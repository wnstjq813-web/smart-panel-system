"""
climate_hourly.py — 시간별 기후 데이터 수집 (STEP 13)
"""
import requests
from datetime import datetime
from src.config import now_kst
from src.config import KMA_API_KEY, KAKAO_API_KEY
from src.lightning import fetch_lightning, summarize_lightning

KMA_BASE_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0"

def fetch_hourly_climate(kma_key, nx, ny):
    now    = now_kst()
    result = {}

    # 초단기실황
    try:
        params = {"serviceKey":kma_key,"numOfRows":10,"pageNo":1,"dataType":"JSON",
                  "base_date":now.strftime("%Y%m%d"),"base_time":now.strftime("%H00"),
                  "nx":nx,"ny":ny}
        r     = requests.get(f"{KMA_BASE_URL}/getUltraSrtNcst", params=params, timeout=10)
        items = r.json()["response"]["body"]["items"]["item"]
        actual = {}
        for item in items:
            cat, val = item["category"], item["obsrValue"]
            if cat=="T1H": actual["temp"] = float(val)
            if cat=="REH": actual["reh"]  = int(float(val))
            if cat=="WSD": actual["wsd"]  = float(val)
            if cat=="PTY": actual["pty"]  = val
            if cat=="RN1": actual["pop"]  = float(val) if val != "강수없음" else 0.0
        actual["lgt"]    = 0
        actual["source"] = "actual"
        result[now.hour] = actual
        print(f"[시간기후] 실황 수집: {now.hour}시 → {actual.get('temp','?')}°C")
    except Exception as e:
        print(f"[시간기후] 실황 수집 실패: {e}")

    # 단기예보
    try:
        base_hours = [2,5,8,11,14,17,20,23]
        cur_h      = now.hour
        base_h     = max([h for h in base_hours if h <= cur_h-1], default=2)
        params = {"serviceKey":kma_key,"numOfRows":300,"pageNo":1,"dataType":"JSON",
                  "base_date":now.strftime("%Y%m%d"),"base_time":f"{base_h:02d}00",
                  "nx":nx,"ny":ny}
        r     = requests.get(f"{KMA_BASE_URL}/getVilageFcst", params=params, timeout=10)
        items = r.json()["response"]["body"]["items"]["item"]
        fcst  = {}
        for item in items:
            if item["fcstDate"] != now.strftime("%Y%m%d"): continue
            h   = int(item["fcstTime"][:2])
            cat = item["category"]
            val = item["fcstValue"]
            if h not in fcst: fcst[h] = {}
            fcst[h][cat] = val
        for h, cats in fcst.items():
            if h in result: continue
            result[h] = {"temp":float(cats.get("TMP",15)),"pop":float(cats.get("POP",0)),
                         "reh":float(cats.get("REH",60)),"wsd":float(cats.get("WSD",2)),
                         "pty":cats.get("PTY","0"),"lgt":int(cats.get("LGT",0)),"source":"forecast"}
        print(f"[시간기후] 예보 수집: {len(fcst)}시간분")
    except Exception as e:
        print(f"[시간기후] 예보 수집 실패: {e}")

    # 낙뢰 병합
    try:
        lgt_data    = fetch_lightning(kma_key=KMA_API_KEY, kakao_key=KAKAO_API_KEY, now=now)
        lgt_summary = summarize_lightning(lgt_data)
        if lgt_summary["detected"] and now.hour in result:
            result[now.hour]["lgt"] = lgt_summary["count_10min"]
    except Exception as e:
        print(f"[시간기후] 낙뢰 병합 실패: {e}")

    return result

def fill_missing_hours(hourly_climate):
    if not hourly_climate: return {}
    filled = dict(hourly_climate)
    hours  = sorted(filled.keys())
    for h in range(24):
        if h in filled: continue
        prev = max((x for x in hours if x < h), default=None)
        nxt  = min((x for x in hours if x > h), default=None)
        if prev is not None and nxt is not None:
            p, n  = filled[prev], filled[nxt]
            ratio = (h-prev) / (nxt-prev)
            filled[h] = {"temp":  round(p["temp"] +(n["temp"] -p["temp"]) *ratio,1),
                         "pop":   round(p["pop"]  +(n["pop"]  -p["pop"])  *ratio,1),
                         "reh":   round(p["reh"]  +(n["reh"]  -p["reh"])  *ratio,1),
                         "wsd":   round(p["wsd"]  +(n["wsd"]  -p["wsd"])  *ratio,1),
                         "pty":p["pty"],"lgt":0,"source":"interpolated"}
        elif prev is not None:
            filled[h] = dict(filled[prev]); filled[h]["source"] = "interpolated"
        elif nxt is not None:
            filled[h] = dict(filled[nxt]);  filled[h]["source"] = "interpolated"
    return filled
