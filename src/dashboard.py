"""
dashboard.py — 대시보드 업데이트 모듈
수정: df_staged 파라미터 추가
  - 공개된 시간(df_sim): 실제 데이터 표시
  - 미공개 시간(df_staged): staged 예측값으로 채움
  - df_sim이 없거나 부족해도 staged로 대체 → 에러 없이 동작
"""
import json
import pandas as pd
from datetime import datetime
from src.config import now_kst
from src.config import (KMA_API_KEY, KAKAO_API_KEY, GITHUB_TOKEN,
                         DASHBOARD_REPO, PANEL_CONFIG, WARN_KW, DANGER_KW, CITY)
from src.kma_weather import get_grid
from src.lightning import fetch_lightning, summarize_lightning
from src.climate_hourly import fetch_hourly_climate, fill_missing_hours
from src.calendar_builder import (get_historical_averages, fetch_forecast_calendar,
                                   build_calendar, build_daily_actual)
from src.github_utils import github_push_file

def _row_to_hourly(row, h, hourly_climate):
    """DataFrame 행 → hourly dict 변환"""
    clm = hourly_climate.get(h, {})
    return {
        "hour":           h,
        "total_load_kw":  round(float(row["total_load_kw"]), 3),
        "status":         str(row.get("panel_status","normal")),
        "accident":       str(row.get("accident_type","none")),
        "temperature":    clm.get("temp",  float(row.get("temperature", 15))),
        "humidity":       clm.get("reh",   float(row.get("humidity", 60))),
        "precipitation":  clm.get("pop",   0.0),
        "wind_speed":     clm.get("wsd",   0.0),
        "pty":            clm.get("pty",   "0"),
        "lightning":      clm.get("lgt",   0),
        "climate_source": clm.get("source","csv"),
        "data_type":      row.get("_data_type", "actual"),
    }

def build_hourly(df_sim, df_staged, now, hourly_climate):
    """
    공개된 시간(df_sim) + 미공개 시간(df_staged) 합쳐서 24시간 구성
    df_sim 없으면 df_staged 전체 사용
    """
    today_str = now.strftime("%Y-%m-%d")
    released  = {}   # hour → row
    staged    = {}   # hour → row

    # 공개된 오늘 데이터
    if df_sim is not None and len(df_sim) > 0:
        df_today = df_sim[df_sim["datetime"].astype(str).str.startswith(today_str)]
        for _, row in df_today.iterrows():
            h = int(str(row["datetime"])[11:13])
            r = row.to_dict()
            r["_data_type"] = "actual"
            released[h] = r

    # staged 데이터 (미공개 시간 채우기용)
    if df_staged is not None and len(df_staged) > 0:
        df_s = df_staged[df_staged["datetime"].astype(str).str.startswith(today_str)]
        for _, row in df_s.iterrows():
            h = int(str(row["datetime"])[11:13])
            r = row.to_dict()
            r["_data_type"] = "staged"
            staged[h] = r

    hourly = []
    for h in range(24):
        if h in released:
            hourly.append(_row_to_hourly(released[h], h, hourly_climate))
        elif h in staged:
            hourly.append(_row_to_hourly(staged[h], h, hourly_climate))
        # 둘 다 없으면 해당 시간 건너뜀 (대시보드가 빈 칸으로 처리)

    return hourly

def build_dashboard_data(prediction, weather, df_sim, metrics,
                          models, feature_names, df_staged=None):
    now = now_kst()

    # 낙뢰
    lgt_data    = fetch_lightning(kma_key=KMA_API_KEY, kakao_key=KAKAO_API_KEY, now=now)
    lgt_summary = summarize_lightning(lgt_data)

    # 시간별 기후
    NX, NY         = get_grid(CITY)
    hourly_climate = fetch_hourly_climate(KMA_API_KEY, NX, NY)
    hourly_climate = fill_missing_hours(hourly_climate)

    # hourly 구성 (실제 + staged 혼합)
    hourly = build_hourly(df_sim, df_staged, now, hourly_climate)

    # 사고 이력 — df_sim 기반 (공개된 것만)
    accident_log = []
    df_acc_src   = df_sim  # 공개된 누적 데이터에서만 이력 표시
    if df_acc_src is not None and len(df_acc_src) > 0:
        for _, row in df_acc_src[df_acc_src["accident_type"] != "none"].tail(20).iterrows():
            accident_log.append({
                "datetime": str(row["datetime"]),
                "type":     str(row["accident_type"]),
                "severity": str(row.get("accident_severity", "info")),
                "circuit":  str(row.get("accident_circuit", "-")),
            })

    # 달력 생성
    hist       = get_historical_averages(df_sim)
    fc_this    = fetch_forecast_calendar(NX, NY, KMA_API_KEY, now.year, now.month)
    cal_this   = build_calendar(now.year, now.month, fc_this, hist,
                                models, feature_names, WARN_KW, DANGER_KW)
    next_month = now.month % 12 + 1
    next_year  = now.year + (1 if now.month == 12 else 0)
    cal_next   = build_calendar(next_year, next_month, {}, hist,
                                models, feature_names, WARN_KW, DANGER_KW)
    daily_actual = build_daily_actual(df_sim)

    return {
        "updated_at":          now.isoformat(),
        "panel_config":        PANEL_CONFIG,
        "current": {
            "total_load_kw":   prediction["total_load_kw"],
            "total_current_a": prediction["total_current_a"],
            "load_ratio":      prediction["load_ratio"],
            "status":          prediction["status"],
            "warn_kw":         WARN_KW,
            "danger_kw":       DANGER_KW,
        },
        "weather":             weather,
        "circuits":            prediction["circuits"],
        "hourly":              hourly,
        "accident_log":        accident_log,
        "model_metrics":       metrics if metrics else {},
        "lightning":           lgt_summary,
        "calendar":            cal_this,
        "calendar_month":      f"{now.year}년 {now.month}월",
        "next_calendar":       cal_next,
        "next_calendar_month": f"{next_year}년 {next_month}월",
        "daily_actual":        daily_actual,
    }

def update_dashboard(prediction, weather, df_sim, metrics,
                     models, feature_names, df_staged=None):
    print("[대시보드] 업데이트 중...")
    data = build_dashboard_data(prediction, weather, df_sim, metrics,
                                 models, feature_names, df_staged=df_staged)
    ok   = github_push_file(
        content_str=json.dumps(data, ensure_ascii=False, indent=2),
        repo_path="dashboard_data.json",
        commit_msg=f"[스마트분전반] {now_kst().strftime('%Y-%m-%d %H:%M')} 업데이트",
        token=GITHUB_TOKEN,
        repo=DASHBOARD_REPO,
    )
    if ok:
        print(f"[대시보드] 완료 → https://wnstjq813-web.github.io/smart-panel")
    return ok
