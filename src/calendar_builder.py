"""
calendar_builder.py — 달력 생성 모듈 (STEP 14)
ASOS 캐시 방식으로 변경 — GitHub에 저장된 캐시 우선 사용
"""
import requests
import calendar as cal_lib
from datetime import datetime
from src.config import now_kst
import pandas as pd
from src.config import KMA_API_KEY, GITHUB_TOKEN, GITHUB_REPO, WARN_KW, DANGER_KW
from src.ml_trainer import build_features

KMA_FCST_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"

# ── 날씨 아이콘 ───────────────────────────────────────
def _get_day_icon(pty, sky):
    if pty in ["1","4"]: return "🌧"
    if pty == "2":        return "🌨"
    if pty == "3":        return "❄️"
    if sky == "1":        return "☀️"
    if sky == "3":        return "⛅"
    return "☁️"

# ── 일별 실적 집계 ────────────────────────────────────
def build_daily_actual(df_sim):
    """CSV 누적 데이터 → 날짜별 실적 집계"""
    result = {}
    if df_sim is None or len(df_sim) == 0:
        return result
    try:
        df = df_sim.copy()
        df["_dt"]   = pd.to_datetime(df["datetime"])
        df["_date"] = df["_dt"].dt.strftime("%Y-%m-%d")
        for date, grp in df.groupby("_date"):
            acc_count = int((grp["accident_type"] != "none").sum())
            if   (grp["panel_status"] == "danger").any(): status = "danger"
            elif (grp["panel_status"] == "warn").any():   status = "warn"
            else:                                         status = "normal"

            # 사고 상세 목록 (달력 클릭 시 표시용)
            acc_list = []
            for _, row in grp[grp["accident_type"] != "none"].iterrows():
                acc_list.append({
                    "hour":     int(str(row["datetime"])[11:13]),
                    "type":     str(row["accident_type"]),
                    "severity": str(row.get("accident_severity","info")),
                    "circuit":  str(row.get("accident_circuit","none")),
                    "load_kw":  round(float(row["total_load_kw"]),3),
                    "current_a":round(float(row["total_current_a"]),2),
                    "voltage_v":round(float(row.get("supply_voltage_v",220)),1),
                })

            result[date] = {
                "avg_load":       round(float(grp["total_load_kw"].mean()), 3),
                "peak_load":      round(float(grp["total_load_kw"].max()),  3),
                "avg_temp":       round(float(grp["temperature"].mean()),   1),
                "avg_reh":        round(float(grp["humidity"].mean()),      1),
                "accident_count": acc_count,
                "accident_list":  acc_list,   # ← 달력 클릭용 상세 목록
                "status":         status,
                "data_type":      "actual",
            }
    except Exception as e:
        print(f"[일별실적] 집계 오류: {e}")
    return result

# ── KMA 단기예보 달력 ─────────────────────────────────
def fetch_forecast_calendar(nx, ny, api_key, year, month):
    result = {}
    if not api_key: return result
    now        = now_kst()
    base_hours = [2,5,8,11,14,17,20,23]
    base_h     = max([h for h in base_hours if h <= now.hour-1], default=2)
    params = {"serviceKey":api_key,"numOfRows":1000,"pageNo":1,"dataType":"JSON",
              "base_date":now.strftime("%Y%m%d"),"base_time":f"{base_h:02d}00","nx":nx,"ny":ny}
    try:
        resp  = requests.get(KMA_FCST_URL, params=params, timeout=10)
        items = resp.json()["response"]["body"]["items"]["item"]
    except:
        return result

    day_data = {}
    for item in items:
        fd = item["fcstDate"]
        d, m, y = int(fd[6:8]), int(fd[4:6]), int(fd[:4])
        if y != year or m != month: continue
        if d not in day_data:
            day_data[d] = {"temps":[],"pops":[],"rehs":[],"wsds":[],"skys":[],"ptys":[]}
        cat, val = item["category"], item["fcstValue"]
        if cat=="TMP": day_data[d]["temps"].append(float(val))
        if cat=="POP": day_data[d]["pops"].append(float(val))
        if cat=="REH": day_data[d]["rehs"].append(float(val))
        if cat=="WSD": day_data[d]["wsds"].append(float(val))
        if cat=="SKY": day_data[d]["skys"].append(val)
        if cat=="PTY": day_data[d]["ptys"].append(val)

    for d, v in day_data.items():
        if not v["temps"]: continue
        pty = max(set(v["ptys"]), key=v["ptys"].count) if v["ptys"] else "0"
        sky = max(set(v["skys"]), key=v["skys"].count) if v["skys"] else "1"
        result[d] = {
            "icon":     _get_day_icon(pty, sky),
            "type":     "forecast",
            "max_temp": round(max(v["temps"]), 1),
            "min_temp": round(min(v["temps"]), 1),
            "avg_pop":  round(sum(v["pops"])/len(v["pops"]), 1) if v["pops"] else 0,
            "avg_reh":  round(sum(v["rehs"])/len(v["rehs"]), 1) if v["rehs"] else 0,
            "avg_wsd":  round(sum(v["wsds"])/len(v["wsds"]), 1) if v["wsds"] else 0,
        }
    return result

# ── 하루 평균 부하 예측 ───────────────────────────────
def predict_day_load(year, month, day, avg_temp, avg_reh, models, feature_names):
    if not models or "total_load_kw" not in models:
        return 0.0
    season_map = {1:"winter",2:"winter",3:"spring",4:"spring",5:"spring",
                  6:"summer",7:"summer",8:"summer",9:"autumn",10:"autumn",11:"autumn",12:"winter"}
    slot_map   = {**{h:"night"   for h in list(range(0,7))+[22,23]},
                  **{h:"commute" for h in [7,8]},
                  **{h:"work_am" for h in [9,10,11]},
                  12:"lunch",
                  **{h:"work_pm" for h in [13,14,15,16,17]},
                  **{h:"evening" for h in [18,19,20,21]}}
    dt       = datetime(year, month, day)
    season   = season_map[month]
    day_type = "weekend" if dt.weekday() >= 5 else "weekday"
    loads = []
    for hour in range(24):
        slot = slot_map.get(hour, "work_am")
        occ  = 0.0 if slot == "night" else (0.1 if day_type == "weekend" else 0.85)
        row  = pd.DataFrame([{
            "datetime":dt.replace(hour=hour).isoformat(),"temperature":avg_temp,
            "humidity":avg_reh,"weather_code":"clear","is_thunder":0,
            "season":season,"time_slot":slot,"day_type":day_type,
            "special_event":"none","occupancy_rate":occ,
        }])
        X = build_features(row)
        loads.append(float(models["total_load_kw"].predict(X)[0]))
    return round(sum(loads)/len(loads), 3)

# ── 달력 딕셔너리 생성 ────────────────────────────────
def build_calendar(year, month, forecast_data, hist_data, models, feature_names, warn_kw, danger_kw):
    days_in_month = cal_lib.monthrange(year, month)[1]
    result = {}
    for day in range(1, days_in_month+1):
        if day in forecast_data:
            fd       = forecast_data[day]
            avg_temp = (fd["max_temp"] + fd["min_temp"]) / 2
            avg_reh  = fd.get("avg_reh", 60)
            avg_load = predict_day_load(year, month, day, avg_temp, avg_reh, models, feature_names)
            entry    = {**fd, "avg_load": avg_load}
        else:
            key      = f"{month}-{day}"
            hd       = hist_data.get(key, {})
            avg_temp = hd.get("avg_temp", 15.0)
            avg_reh  = hd.get("avg_reh",  60.0)
            avg_load = predict_day_load(year, month, day, avg_temp, avg_reh, models, feature_names)
            entry    = {
                "icon":     hd.get("icon", ""),
                "type":     "average",
                "max_temp": hd.get("max_temp", avg_temp+5),
                "min_temp": hd.get("min_temp", avg_temp-5),
                "avg_pop":  hd.get("avg_pop",  20),
                "avg_reh":  avg_reh,
                "avg_wsd":  hd.get("avg_wsd",  3.0),
                "feel_temp":hd.get("feel_temp", avg_temp),
                "avg_load": avg_load,
            }
        entry["alert"] = ("🔴 위험" if entry["avg_load"] >= danger_kw
                          else "🟡 경고" if entry["avg_load"] >= warn_kw
                          else "🟢 정상")
        result[day] = entry
    return result

# ── ASOS 캐시 사용 (GitHub 저장소에서 읽기) ──────────
def get_historical_averages(df_sim=None, token=None, repo=None):
    """
    GitHub에 저장된 ASOS 캐시 우선 사용
    없으면 최초 전체 수집 후 저장
    API 호출 없이 즉시 반환 (매일 자정 update_asos_cache_daily가 갱신)
    """
    from src.github_utils import get_asos_avg_data
    return get_asos_avg_data(KMA_API_KEY, token or GITHUB_TOKEN, repo or GITHUB_REPO)
