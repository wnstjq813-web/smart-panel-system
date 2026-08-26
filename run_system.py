"""
run_system.py — 스마트 분전반 시스템 실행 진입점
[수정] backfill_rows_bulk import 제거 (github_utils에 없는 함수 → ImportError 원인)
       release_hourly_row가 0~현재시간 전체를 처리하므로 별도 backfill 불필요
"""
import os
from src.config import (CITY, KMA_API_KEY, GITHUB_TOKEN,
                         TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, now_kst)
from src.kma_weather import get_grid, fetch_current_weather
from src.github_utils import (fetch_simulation_data, update_asos_cache_daily,
                               fetch_staged_csv, release_hourly_row, DATA_REPO)
from src.ml_trainer import train_models
from src.predictor import predict_load
from src.telegram_bot import (send_telegram, build_daily_report,
                               build_alert_message, build_accident_alert)
from src.lightning import fetch_lightning, build_lightning_alert
from src.dashboard import update_dashboard

MODE       = os.environ.get("RUN_MODE", "monitor")
EVENT_NAME = os.environ.get("GITHUB_EVENT_NAME", "")


def _pick_train_df(df_sim, df_staged):
    """학습용 DataFrame 선택 — 누적 부족 시 staged 보완"""
    import pandas as pd
    if df_sim is not None and len(df_sim) >= 24:
        print(f"[학습] 누적 CSV 사용: {len(df_sim)}행")
        return df_sim
    if df_staged is not None:
        if df_sim is not None and len(df_sim) > 0:
            merged = pd.concat([df_sim, df_staged], ignore_index=True)
            merged = merged.drop_duplicates("datetime")
            print(f"[학습] staged 보완 사용: {len(merged)}행")
            return merged
        print(f"[학습] staged 단독 사용: {len(df_staged)}행")
        return df_staged
    print("[학습] 데이터 없음")
    return df_sim


def run_daily():
    now = now_kst()
    print(f"\n{'='*50}\n 일일 파이프라인: {now.strftime('%Y-%m-%d %H:%M:%S')} KST\n{'='*50}")

    print("\n[0/4] ASOS 기후 캐시 업데이트...")
    update_asos_cache_daily(KMA_API_KEY, GITHUB_TOKEN, DATA_REPO)

    df_sim, latest_summary = fetch_simulation_data()
    df_staged              = fetch_staged_csv(GITHUB_TOKEN, DATA_REPO)
    df_train               = _pick_train_df(df_sim, df_staged)

    models, metrics, feature_names = train_models(df_train)
    NX, NY          = get_grid(CITY)
    current_weather = fetch_current_weather(NX, NY, KMA_API_KEY)
    prediction      = predict_load(current_weather, models, feature_names,
                                   latest_summary, now=now)
    update_dashboard(prediction, current_weather, df_sim, metrics,
                     models, feature_names, df_staged=df_staged)
    print(f"\n완료: {prediction['total_load_kw']}kW / {prediction['status']}")


def run_report():
    now = now_kst()
    print(f"\n[리포트] {now.strftime('%Y-%m-%d %H:%M:%S')} KST 리포트 전송 중...")
    df_sim, latest_summary = fetch_simulation_data()
    df_staged              = fetch_staged_csv(GITHUB_TOKEN, DATA_REPO)
    df_train               = _pick_train_df(df_sim, df_staged)

    models, metrics, feature_names = train_models(df_train)
    NX, NY  = get_grid(CITY)
    weather = fetch_current_weather(NX, NY, KMA_API_KEY)
    pred    = predict_load(weather, models, feature_names, latest_summary, now=now)
    send_telegram(build_daily_report(pred, weather, metrics),
                  TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
    print("[리포트] 전송 완료")


def run_monitor():
    now = now_kst()
    print(f"\n[모니터] {now.strftime('%Y-%m-%d %H:%M')} KST")

    # ── 1. staged 미공개 행 공개 (누락분 자동 복구 포함) ──
    released = release_hourly_row(hour=now.hour, token=GITHUB_TOKEN, repo=DATA_REPO)

    # ── 2. 사고 알림 ──
    if released:
        acc = released.get("accident_type", "none")
        sev = released.get("accident_severity", "none")
        if acc != "none" and sev in ["warn", "critical"]:
            send_telegram(build_accident_alert(released),
                          TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
            print(f"[사고 알림] {acc} / {sev}")

    # ── 3. RF 예측 + 부하 경보 ──
    df_sim, latest_summary = fetch_simulation_data()
    df_staged              = fetch_staged_csv(GITHUB_TOKEN, DATA_REPO)
    df_train               = _pick_train_df(df_sim, df_staged)

    models, metrics, feature_names = train_models(df_train)
    NX, NY  = get_grid(CITY)
    weather = fetch_current_weather(NX, NY, KMA_API_KEY)
    pred    = predict_load(weather, models, feature_names, latest_summary, now=now)

    if pred["status"] in ["warn", "danger"]:
        send_telegram(build_alert_message(pred), TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)

    # ── 4. 낙뢰 감지 ──
    lgt = fetch_lightning(kma_key=KMA_API_KEY,
                          kakao_key=os.environ.get("KAKAO_API_KEY", ""),
                          now=now)
    if lgt["detected"] and lgt["danger_level"] in ["danger", "warning"]:
        msg = build_lightning_alert(lgt)
        if msg:
            send_telegram(msg, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)

    # ── 5. 대시보드 갱신 ──
    update_dashboard(pred, weather, df_sim, metrics,
                     models, feature_names, df_staged=df_staged)
    print(f"[모니터] {pred['total_load_kw']}kW / {pred['status']}")


if __name__ == "__main__":
    if MODE == "daily":    run_daily()
    elif MODE == "report": run_report()
    else:                  run_monitor()
