"""
lightning.py — 낙뢰 감지 모듈 (STEP 4)
"""
import requests
import math
from datetime import datetime, timedelta

LGT_BASE_URL   = "http://apis.data.go.kr/1360000/LgtInfoService/getLgt"
KAKAO_GEO_URL  = "https://dapi.kakao.com/v2/local/geo/coord2address.json"

PANEL_LOCATION = {"lat": 36.6008, "lon": 126.6606, "name": "홍성"}

LGT_TYPE_MAP = {"CG":"구름-지면","CC":"구름-구름","IC":"구름내부","GC":"지면-구름"}
LGT_DANGER_KM = 5.0
LGT_WARN_KM   = 20.0
LGT_HIGH_AMP  = 50.0

def haversine_km(lat1, lon1, lat2, lon2):
    R    = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a    = (math.sin(dlat/2)**2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlon/2)**2)
    return R * 2 * math.asin(math.sqrt(a))

def reverse_geocode_kakao(lat, lon, kakao_key):
    if not kakao_key:
        return f"{lat:.4f}°N / {lon:.4f}°E"
    try:
        headers = {"Authorization": f"KakaoAK {kakao_key}"}
        params  = {"x": lon, "y": lat, "input_coord": "WGS84"}
        resp    = requests.get(KAKAO_GEO_URL, headers=headers, params=params, timeout=5)
        data    = resp.json()
        docs    = data.get("documents", [])
        if not docs: return f"{lat:.4f}°N / {lon:.4f}°E"
        addr   = docs[0]
        road   = addr.get("road_address")
        region = addr.get("address")
        if road:   return road.get("address_name", "")
        if region: return region.get("address_name", "")
        return f"{lat:.4f}°N / {lon:.4f}°E"
    except Exception as e:
        print(f"[카카오] 역지오코딩 실패: {e}")
        return f"{lat:.4f}°N / {lon:.4f}°E"

def fetch_lightning(kma_key, kakao_key, now=None, panel_lat=None, panel_lon=None):
    if now is None:      now       = datetime.now()
    if panel_lat is None: panel_lat = PANEL_LOCATION["lat"]
    if panel_lon is None: panel_lon = PANEL_LOCATION["lon"]

    empty = {"detected":False,"events":[],"closest":None,"count_10min":0,"danger_level":"none"}
    if not kma_key: return empty

    dt_query  = (now - timedelta(minutes=10)).strftime("%Y%m%d%H%M")
    all_items = []
    for lgt_type_code in [1, 2]:
        params = {"serviceKey":kma_key,"numOfRows":100,"pageNo":1,
                  "dataType":"JSON","lgtType":lgt_type_code,"dateTime":dt_query}
        try:
            resp        = requests.get(LGT_BASE_URL, params=params, timeout=10)
            data        = resp.json()
            result_code = data.get("response",{}).get("header",{}).get("resultCode","")
            if result_code == "03": continue
            if result_code != "00":
                print(f"[낙뢰API] lgtType={lgt_type_code} 오류 {result_code}")
                continue
            items_raw = data["response"]["body"]["items"].get("item", [])
            if isinstance(items_raw, dict): items_raw = [items_raw]
            for item in items_raw:
                item["_lgtTypeCode"] = lgt_type_code
            all_items.extend(items_raw)
        except Exception as e:
            print(f"[낙뢰API] lgtType={lgt_type_code} 요청 실패: {e}")

    if not all_items: return empty

    events = []
    for item in all_items:
        try:
            lat        = float(item.get("wgs84Lat", 0))
            lon        = float(item.get("wgs84Lon", 0))
            amp        = float(item.get("intensity", 0))
            type_code  = int(item.get("_lgtTypeCode", 1))
            sensors    = int(item.get("sensorCount", 0))
            dt_str     = str(item.get("dateTime", ""))
            ltype      = "CG" if type_code == 1 else "CC"
            dist_km    = haversine_km(panel_lat, panel_lon, lat, lon)
            address    = reverse_geocode_kakao(lat, lon, kakao_key)
            polarity   = "정극성(+)" if amp >= 0 else "부극성(-)"
            if ltype == "CG" and dist_km <= LGT_DANGER_KM: level = "danger"
            elif dist_km <= LGT_WARN_KM:                    level = "warning"
            else:                                           level = "watch"
            try:
                dt       = datetime.strptime(dt_str, "%Y%m%d%H%M%S")
                dt_label = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                dt_label = dt_str
            events.append({"datetime":dt_label,"latitude":round(lat,4),"longitude":round(lon,4),
                            "address":address,"type":ltype,"type_label":LGT_TYPE_MAP.get(ltype,ltype),
                            "amplitude_ka":round(amp,1),"polarity":polarity,"sensor_count":sensors,
                            "distance_km":round(dist_km,2),"danger_level":level})
        except Exception as e:
            print(f"[낙뢰API] 항목 파싱 오류: {e}")

    if not events: return empty
    events.sort(key=lambda x: x["distance_km"])
    closest = events[0]
    levels  = [e["danger_level"] for e in events]
    if "danger"  in levels: overall = "danger"
    elif "warning" in levels: overall = "warning"
    elif "watch"   in levels: overall = "watch"
    else:                     overall = "none"
    return {"detected":True,"events":events,"closest":closest,"count_10min":len(events),"danger_level":overall}

def get_lightning_multiplier(lgt_data):
    if not lgt_data or not lgt_data.get("detected"): return 1.0
    closest = lgt_data.get("closest")
    if not closest: return 1.0
    ltype   = closest.get("type","CC")
    dist_km = closest.get("distance_km", 999)
    amp_ka  = abs(closest.get("amplitude_ka", 0))
    if ltype == "CG" and dist_km <= LGT_DANGER_KM: mult = 25.0
    elif ltype == "CG" and dist_km <= LGT_WARN_KM: mult = 15.0
    else:                                           mult = 6.0
    if amp_ka >= LGT_HIGH_AMP: mult *= 1.5
    return round(mult, 2)

def build_lightning_alert(lgt_data):
    if not lgt_data or not lgt_data.get("detected"): return ""
    closest = lgt_data["closest"]
    level   = lgt_data["danger_level"]
    count   = lgt_data["count_10min"]
    if level == "danger":   header = "⚡ <b>[위험] 낙뢰 감지 — 즉시 확인</b>"
    elif level == "warning": header = "🟡 <b>[주의] 낙뢰 감지 — 모니터링 강화</b>"
    else:                    header = "🔵 <b>[관찰] 원거리 낙뢰 감지</b>"
    if level == "danger":
        check_circuits = "\n⚠️ c3 콘센트A(PC) / c6 서버·네트워크 회로 점검 권고\n⚠️ SPD(서지보호장치) 동작 여부 확인"
    elif level == "warning":
        check_circuits = "\n⚠️ 서버·민감 장비 상태 모니터링"
    else:
        check_circuits = ""
    return (f"{header}\n{closest.get('datetime','-')}\n\n"
            f"📍 위치: {closest.get('address','-')}\n"
            f"🏢 분전반까지: <b>{closest.get('distance_km','-')}km</b>\n\n"
            f"⚡ 종류: {closest.get('type_label','-')} ({closest.get('type','-')})\n"
            f"💥 강도: {closest.get('amplitude_ka',0):+.1f} kA ({closest.get('polarity','-')})\n"
            f"📡 감지 센서: {closest.get('sensor_count','-')}개\n"
            f"📊 최근 10분 감지: {count}건{check_circuits}")

def summarize_lightning(lgt_data):
    if not lgt_data or not lgt_data.get("detected"):
        return {"detected":False,"danger_level":"none","count_10min":0,
                "closest_dist_km":None,"closest_type":None,"closest_amp_ka":None,
                "closest_address":None,"closest_datetime":None,"events":[]}
    closest = lgt_data.get("closest", {})
    return {"detected":True,"danger_level":lgt_data.get("danger_level","none"),
            "count_10min":lgt_data.get("count_10min",0),
            "closest_dist_km":closest.get("distance_km"),
            "closest_type":closest.get("type"),
            "closest_type_label":closest.get("type_label"),
            "closest_amp_ka":closest.get("amplitude_ka"),
            "closest_polarity":closest.get("polarity"),
            "closest_address":closest.get("address"),
            "closest_datetime":closest.get("datetime"),
            "events":lgt_data.get("events",[])[:5]}
