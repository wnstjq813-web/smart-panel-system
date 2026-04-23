"""
run_system.py — 스마트 분전반 시스템 실행 진입점
GitHub Actions cron: 자정(일일), 09:00(리포트), 매시간(모니터링)
"""
import os
from datetime import datetime
from src.config import (CITY, KMA_API_KEY, GITHUB_TOKEN, GITHUB_REPO,
                         TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
from src.kma_weather import get_grid, fetch_current_weather
from src.github_utils import fetch_simulation_data, update_asos_cache_daily
from src.ml_trainer import train_models
from src.predictor import predict_load
from src.telegram_bot import send_telegram, build_daily_report, build_alert_message
from src.lightning import fetch_lightning, build_lightning_alert
from src.dashboard import update_dashboard

MODE = os.environ.get("RUN_MODE", "monitor")

def run_daily():
    print(f"\n{'='*50}\n 일일 파이프라인: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{'='*50}")

    # ASOS 캐시 일별 업데이트 (어제 하루치 추가, 가장 오래된 하루 삭제)
    print("\n[0/4] ASOS 기후 캐시 업데이트...")
    update_asos_cache_daily(KMA_API_KEY, GITHUB_TOKEN, GITHUB_REPO)

    df_sim, latest_summary         = fetch_simulation_data()
    models, metrics, feature_names = train_models(df_sim)
    NX, NY                         = get_grid(CITY)
    current_weather                = fetch_current_weather(NX, NY, KMA_API_KEY)
    prediction                     = predict_load(current_weather, models, feature_names, latest_summary)
    update_dashboard(prediction, current_weather, df_sim, metrics, models, feature_names)
    print(f"\n완료: {prediction['total_load_kw']}kW / {prediction['status']}")

def run_report():
    print("\n[리포트] 오전 9시 리포트 전송 중...")
    df_sim, latest_summary         = fetch_simulation_data()
    models, metrics, feature_names = train_models(df_sim)
    NX, NY                         = get_grid(CITY)
    weather                        = fetch_current_weather(NX, NY, KMA_API_KEY)
    pred                           = predict_load(weather, models, feature_names, latest_summary)
    msg                            = build_daily_report(pred, weather, metrics)
    send_telegram(msg, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
    print("[리포트] 전송 완료")

def run_monitor():
    print(f"\n[모니터] {datetime.now().strftime('%H:%M')} 경보 모니터링 시작")
    df_sim, latest_summary         = fetch_simulation_data()
    models, metrics, feature_names = train_models(df_sim)
    NX, NY                         = get_grid(CITY)
    weather                        = fetch_current_weather(NX, NY, KMA_API_KEY)
    pred                           = predict_load(weather, models, feature_names, latest_summary)
    status                         = pred["status"]

    if status in ["warn","danger"]:
        send_telegram(build_alert_message(pred), TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)

    lgt_data = fetch_lightning(kma_key=KMA_API_KEY,
                                kakao_key=os.environ.get("KAKAO_API_KEY",""),
                                now=datetime.now())
    if lgt_data["detected"] and lgt_data["danger_level"] in ["danger","warning"]:
        lgt_msg = build_lightning_alert(lgt_data)
        if lgt_msg:
            send_telegram(lgt_msg, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)

    update_dashboard(pred, weather, df_sim, metrics, models, feature_names)
    print(f"[모니터] {pred['total_load_kw']}kW / {status}")

if __name__ == "__main__":
    if MODE == "daily":   run_daily()
    elif MODE == "report": run_report()
    else:                  run_monitor()
