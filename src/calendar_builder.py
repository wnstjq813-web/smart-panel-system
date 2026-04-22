"""
calendar_builder.py — 달력 생성 모듈 (STEP 14)
KMA 단기예보(~5일) + ASOS 10년 과거 평균(나머지 날) 혼합
"""
import requests
import calendar as cal_lib
import time
from collections import defaultdict
from datetime import datetime
import pandas as pd
from src.config import KMA_API_KEY, WARN_KW, DANGER_KW
from src.ml_trainer import build_features

ASOS_STN_ID   = 235   # 보령 (홍성 인근 최근접 ASOS 지점)
ASOS_BASE_URL = "http://apis.data.go.kr/1360000/AsosDalyInfoService/getWthrDataList"
ASOS_YEARS    = 10    # 최근 10년치 수집
KMA_FCST_URL  = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"

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
            result[date] = {
                "avg_load":       round(float(grp["total_load_kw"].mean()), 3),
                "peak_load":      round(float(grp["total_load_kw"].max()),  3),
                "avg_temp":       round(float(grp["temperature"].mean()),   1),
                "avg_reh":        round(float(grp["humidity"].mean()),      1),
                "accident_count": acc_count,
                "status":         status,
                "data_type":      "actual",
            }
    except Exception as e:
        print(f"[일별실적] 집계 오류: {e}")
    return result

# ── KMA 단기예보 달력 ─────────────────────────────────
def fetch_forecast_calendar(nx, ny, api_key, year, month):
    """KMA 단기예보로 이번달 날씨 수집 → {day: {icon, max_temp, ...}}"""
    result = {}
    if not api_key: return result
    now        = datetime.now()
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
    """24시간 예측 후 평균값 반환"""
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
    """KMA 예보 + ASOS 과거 평균 혼합 달력 생성"""
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

# ── ASOS 10년 과거 기후 평균 ──────────────────────────
def fetch_asos_climate_avg(api_key, stn_id=ASOS_STN_ID, years=ASOS_YEARS):
    """보령(235) ASOS 10년 일자료 → 월-일별 평균 기온/습도"""
    now        = datetime.now()
    end_year   = now.year - 1
    start_year = end_year - years + 1
    print(f"[ASOS] 보령({stn_id}) {start_year}~{end_year}년 수집 시작...")

    day_records = defaultdict(lambda: {"temps":[],"maxs":[],"mins":[],"rehs":[]})

    for year in range(start_year, end_year+1):
        params = {"serviceKey":api_key,"numOfRows":400,"pageNo":1,"dataType":"JSON",
                  "dataCd":"ASOS","dateCd":"DAY",
                  "startDt":f"{year}0101","endDt":f"{year}1231","stnIds":stn_id}
        items = []
        for attempt in range(2):
            try:
                resp = requests.get(ASOS_BASE_URL, params=params, timeout=30)
                data = resp.json()
                code = data.get("response",{}).get("header",{}).get("resultCode","")
                if code != "00":
                    print(f"  [ASOS] {year}년 오류 {code}")
                    break
                items = data["response"]["body"]["items"].get("item",[])
                if isinstance(items, dict): items = [items]
                print(f"  [ASOS] {year}년 완료 ({len(items)}건)")
                break
            except Exception as e:
                print(f"  [ASOS] {year}년 {'재시도' if attempt else '요청'} 실패: {e}")
                if attempt == 0: time.sleep(3)

        for item in items:
            dt_str = str(item.get("tm","")).replace("-","")
            if len(dt_str) < 8: continue
            m, d = int(dt_str[4:6]), int(dt_str[6:8])
            key  = f"{m}-{d}"
            try:
                avg = item.get("avgTa"); mx = item.get("maxTa")
                mn  = item.get("minTa"); reh = item.get("avgRhm")
                if avg not in (None,""): day_records[key]["temps"].append(float(avg))
                if mx  not in (None,""): day_records[key]["maxs"].append(float(mx))
                if mn  not in (None,""): day_records[key]["mins"].append(float(mn))
                if reh not in (None,""): day_records[key]["rehs"].append(float(reh))
            except: continue

    result = {}
    for key, v in day_records.items():
        if not v["temps"]: continue
        avg_t = round(sum(v["temps"])/len(v["temps"]), 1)
        result[key] = {
            "avg_temp":  avg_t,
            "max_temp":  round(sum(v["maxs"])/len(v["maxs"]),1) if v["maxs"] else avg_t+5,
            "min_temp":  round(sum(v["mins"])/len(v["mins"]),1) if v["mins"] else avg_t-5,
            "avg_reh":   round(sum(v["rehs"])/len(v["rehs"]),1) if v["rehs"] else 60.0,
            "avg_pop":   20,
            "avg_wsd":   3.0,
            "feel_temp": round(avg_t-0.4, 1),
            "icon":      "",
        }
    print(f"[ASOS] 완료 — {len(result)}개 날짜 평균 계산")
    return result

# ── ASOS 캐시 (하루 1회만 API 호출) ──────────────────
_asos_cache = None

def get_historical_averages(df_sim=None):
    global _asos_cache
    if _asos_cache is not None:
        return _asos_cache
    _asos_cache = fetch_asos_climate_avg(KMA_API_KEY)
    return _asos_cache
