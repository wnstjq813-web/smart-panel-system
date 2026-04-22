"""
kma_weather.py — KMA 날씨 API 모듈 (STEP 3)
"""
import requests
from datetime import datetime, timedelta

KMA_BASE_URL    = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0"
FCST_BASE_TIMES = ["0200","0500","0800","1100","1400","1700","2000","2300"]
SKY_CODE_MAP    = {"1":"clear","3":"partly_cloudy","4":"cloudy"}
PTY_CODE_MAP    = {"0":"none","1":"rainy","2":"sleet","3":"snowy","4":"shower"}

GRID_COORDS = {
    "홍성":(55,103),"서울":(60,127),"부산":(98,76),
    "대구":(89,90), "인천":(55,124),"광주":(58,74),
    "대전":(67,100),"울산":(102,84),"수원":(60,121),"청주":(69,106),
}

def get_grid(city):
    if city not in GRID_COORDS:
        raise ValueError(f"'{city}' 좌표 없음. 사용 가능: {', '.join(GRID_COORDS)}")
    return GRID_COORDS[city]

def get_fcst_base_datetime(now):
    adj = now - timedelta(minutes=15)
    base_time = FCST_BASE_TIMES[0]
    for bt in FCST_BASE_TIMES:
        if int(adj.strftime("%H%M")) >= int(bt):
            base_time = bt
        else:
            break
    if int(adj.strftime("%H%M")) < int(FCST_BASE_TIMES[0]):
        prev = adj - timedelta(days=1)
        return prev.strftime("%Y%m%d"), "2300"
    return adj.strftime("%Y%m%d"), base_time

def get_ncst_base_datetime(now):
    adj = now - timedelta(minutes=15)
    return adj.strftime("%Y%m%d"), adj.strftime("%H") + "00"

def _default_weather(now=None):
    if now is None: now = datetime.now()
    m = now.month
    if m in [3,4,5]:    return {"temperature":15.0,"humidity":55,"weather_code":"partly_cloudy","is_thunder":False}
    elif m in [6,7,8]:  return {"temperature":28.0,"humidity":75,"weather_code":"cloudy","is_thunder":False}
    elif m in [9,10,11]:return {"temperature":16.0,"humidity":60,"weather_code":"clear","is_thunder":False}
    else:               return {"temperature":2.0, "humidity":50,"weather_code":"clear","is_thunder":False}

def fetch_village_forecast(nx, ny, api_key, now=None):
    if now is None: now = datetime.now()
    if not api_key: return {}
    base_date, base_time = get_fcst_base_datetime(now)
    params = {"serviceKey":api_key,"numOfRows":300,"pageNo":1,"dataType":"JSON",
              "base_date":base_date,"base_time":base_time,"nx":nx,"ny":ny}
    try:
        resp  = requests.get(f"{KMA_BASE_URL}/getVilageFcst", params=params, timeout=10)
        data  = resp.json()
        if data["response"]["header"]["resultCode"] != "00": return {}
        items = data["response"]["body"]["items"]["item"]
        hourly = {}
        for item in items:
            key = (item["fcstDate"], item["fcstTime"])
            if key not in hourly: hourly[key] = {}
            hourly[key][item["category"]] = item["fcstValue"]
        today_str = now.strftime("%Y%m%d")
        result = {}
        for (fdate, ftime), vals in hourly.items():
            if fdate != today_str: continue
            hour = int(ftime[:2])
            pty  = vals.get("PTY","0")
            weather_code = PTY_CODE_MAP.get(pty,"rainy") if pty!="0" else SKY_CODE_MAP.get(vals.get("SKY","1"),"clear")
            result[hour] = {"temperature":float(vals.get("TMP",20)),"humidity":int(vals.get("REH",60)),
                            "weather_code":weather_code,"is_thunder":vals.get("LGT","0")=="1"}
        return result
    except Exception as e:
        print(f"[KMA] 단기예보 실패: {e}")
        return {}

def fetch_realtime_weather(nx, ny, api_key, now=None):
    if now is None: now = datetime.now()
    if not api_key: return None
    base_date, base_time = get_ncst_base_datetime(now)
    params = {"serviceKey":api_key,"numOfRows":10,"pageNo":1,"dataType":"JSON",
              "base_date":base_date,"base_time":base_time,"nx":nx,"ny":ny}
    try:
        resp  = requests.get(f"{KMA_BASE_URL}/getUltraSrtNcst", params=params, timeout=10)
        data  = resp.json()
        if data["response"]["header"]["resultCode"] != "00": return None
        items = data["response"]["body"]["items"]["item"]
        vals  = {item["category"]: item["obsrValue"] for item in items}
        pty   = vals.get("PTY","0")
        return {"temperature":float(vals.get("T1H",20)),"humidity":int(float(vals.get("REH",60))),
                "weather_code":PTY_CODE_MAP.get(pty,"clear") if pty!="0" else "clear",
                "is_thunder":vals.get("LGT","0")=="1"}
    except Exception as e:
        print(f"[KMA] 실황 실패: {e}")
        return None

def get_today_weather(nx, ny, api_key, now=None):
    if now is None: now = datetime.now()
    print(f"[KMA] 날씨 조회 중... (NX={nx}, NY={ny})")
    realtime = fetch_realtime_weather(nx, ny, api_key, now)
    hourly   = fetch_village_forecast(nx, ny, api_key, now)
    cur_hour = now.hour
    if realtime:
        current = realtime
        print(f"[KMA] 실황: {current['temperature']}°C / {current['humidity']}% / {current['weather_code']}")
    elif cur_hour in hourly:
        current = hourly[cur_hour]
        print(f"[KMA] 예보값 사용: {current['temperature']}°C")
    else:
        current = _default_weather(now)
        print(f"[KMA] 기본값 사용: {current['temperature']}°C")
    return {**current, "hourly": hourly}

def get_weather_for_hour(weather_data, hour):
    hourly = weather_data.get("hourly", {})
    if hour in hourly: return hourly[hour]
    return {"temperature":weather_data["temperature"],"humidity":weather_data["humidity"],
            "weather_code":weather_data["weather_code"],"is_thunder":weather_data["is_thunder"]}

def fetch_current_weather(nx, ny, api_key, now=None):
    if now is None: now = datetime.now()
    if not api_key: return _default_weather(now)
    adj    = now - timedelta(minutes=15)
    params = {"serviceKey":api_key,"numOfRows":10,"pageNo":1,"dataType":"JSON",
              "base_date":adj.strftime("%Y%m%d"),"base_time":adj.strftime("%H")+"00","nx":nx,"ny":ny}
    try:
        resp  = requests.get(f"{KMA_BASE_URL}/getUltraSrtNcst", params=params, timeout=10)
        data  = resp.json()
        if data["response"]["header"]["resultCode"] != "00": return _default_weather(now)
        items = data["response"]["body"]["items"]["item"]
        vals  = {item["category"]: item["obsrValue"] for item in items}
        pty   = vals.get("PTY","0")
        return {"temperature":float(vals.get("T1H",20)),"humidity":int(float(vals.get("REH",60))),
                "weather_code":PTY_CODE_MAP.get(pty,"clear") if pty!="0" else "clear",
                "is_thunder":vals.get("LGT","0")=="1"}
    except:
        return _default_weather(now)
