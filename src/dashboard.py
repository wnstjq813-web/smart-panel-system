"""
dashboard.py — 대시보드 업데이트 모듈 (STEP 15)
"""
import json
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

def build_dashboard_data(prediction, weather, df_sim, metrics, models, feature_names):
    now = now_kst()

    # 낙뢰
    lgt_data    = fetch_lightning(kma_key=KMA_API_KEY, kakao_key=KAKAO_API_KEY, now=now)
    lgt_summary = summarize_lightning(lgt_data)

    # 시간별 기후
    NX, NY         = get_grid(CITY)
    hourly_climate = fetch_hourly_climate(KMA_API_KEY, NX, NY)
    hourly_climate = fill_missing_hours(hourly_climate)

    # hourly 데이터 구성
    hourly = []
    if df_sim is not None:
        today_str = now.strftime("%Y-%m-%d")
        df_today  = df_sim[df_sim["datetime"].str.startswith(today_str)]
        if len(df_today) == 0:
            df_today = df_sim.tail(24)
        for _, row in df_today.iterrows():
            h   = int(str(row["datetime"])[11:13])
            clm = hourly_climate.get(h, {})
            hourly.append({
                "hour":          h,
                "total_load_kw": round(float(row["total_load_kw"]), 3),
                "status":        str(row["panel_status"]),
                "accident":      str(row.get("accident_type", "none")),
                "temperature":   clm.get("temp",  float(row["temperature"])),
                "humidity":      clm.get("reh",   float(row.get("humidity", 60))),
                "precipitation": clm.get("pop",   0.0),
                "wind_speed":    clm.get("wsd",   0.0),
                "pty":           clm.get("pty",   "0"),
                "lightning":     clm.get("lgt",   0),
                "climate_source":clm.get("source","csv"),
            })

    # 사고 이력
    accident_log = []
    if df_sim is not None:
        for _, row in df_sim[df_sim["accident_type"] != "none"].tail(20).iterrows():
            accident_log.append({
                "datetime": str(row["datetime"]),
                "type":     str(row["accident_type"]),
                "severity": str(row.get("accident_severity", "info")),
                "circuit":  str(row.get("accident_circuit", "-")),
            })

    # 달력 생성
    hist        = get_historical_averages(df_sim)
    fc_this     = fetch_forecast_calendar(NX, NY, KMA_API_KEY, now.year, now.month)
    cal_this    = build_calendar(now.year, now.month, fc_this, hist,
                                 models, feature_names, WARN_KW, DANGER_KW)
    next_month  = now.month % 12 + 1
    next_year   = now.year + (1 if now.month == 12 else 0)
    cal_next    = build_calendar(next_year, next_month, {}, hist,
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

def update_dashboard(prediction, weather, df_sim, metrics, models, feature_names):
    print("[대시보드] 업데이트 중...")
    data = build_dashboard_data(prediction, weather, df_sim, metrics, models, feature_names)
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
