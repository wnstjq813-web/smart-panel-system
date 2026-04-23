"""
github_utils.py — GitHub 데이터 송수신 모듈 (STEP 8·9)
ASOS 10년 기후 캐시 저장/읽기 추가
"""
import requests, base64, json, io, time
from collections import defaultdict
import pandas as pd
from datetime import datetime, timedelta
from src.config import GITHUB_TOKEN, GITHUB_REPO

# ── 기본 GitHub 함수 ──────────────────────────────────

def github_get_file(repo_path, token=None, repo=None):
    token = token or GITHUB_TOKEN
    repo  = repo  or GITHUB_REPO
    url     = f"https://api.github.com/repos/{repo}/contents/{repo_path}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    resp    = requests.get(url, headers=headers)
    if resp.status_code == 200:
        return base64.b64decode(resp.json().get("content","")).decode("utf-8-sig")
    print(f"[GitHub] 읽기 실패 {resp.status_code}: {repo_path}")
    return None

def github_push_file(content_str, repo_path, commit_msg, token=None, repo=None):
    token = token or GITHUB_TOKEN
    repo  = repo  or GITHUB_REPO
    url     = f"https://api.github.com/repos/{repo}/contents/{repo_path}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    sha  = None
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        sha = resp.json().get("sha")
    content_b64 = base64.b64encode(content_str.encode("utf-8-sig")).decode("utf-8")
    payload = {"message": commit_msg, "content": content_b64}
    if sha: payload["sha"] = sha
    resp = requests.put(url, headers=headers, data=json.dumps(payload))
    if resp.status_code in [200, 201]:
        action = "업데이트" if sha else "생성"
        print(f"  [GitHub] {repo_path} {action} 완료")
        return True
    print(f"  [GitHub] 오류 {resp.status_code}: {resp.json().get('message')}")
    return False

def push_simulation_results(csv_path="panel_simulation.csv", token=None, repo=None):
    token    = token or GITHUB_TOKEN
    repo     = repo  or GITHUB_REPO
    now      = datetime.now()
    date_str = now.strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[GitHub] push 시작 ({date_str})")
    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            csv_content = f.read()
        success_csv = github_push_file(
            content_str=csv_content,
            repo_path="data/panel_simulation.csv",
            commit_msg=f"[시뮬레이터] {date_str} 데이터 업데이트",
            token=token, repo=repo,
        )
    except FileNotFoundError:
        print(f"  [GitHub] {csv_path} 파일 없음")
        return False

    df   = pd.read_csv(csv_path)
    last = df.iloc[-1]
    summary = {
        "updated_at":       date_str,
        "last_datetime":    str(last.get("datetime","")),
        "total_load_kw":    round(float(last.get("total_load_kw",0)),3),
        "total_current_a":  round(float(last.get("total_current_a",0)),2),
        "supply_voltage_v": round(float(last.get("supply_voltage_v",220)),1),
        "panel_status":     str(last.get("panel_status","normal")),
        "accident_type":    str(last.get("accident_type","none")),
        "accident_severity":str(last.get("accident_severity","none")),
        "panel_config": {"main_breaker_a":100,"main_capacity_kw":22.0,
                         "warn_kw":15.4,"danger_kw":19.8,"nominal_voltage":220.0,"circuits":9},
        "daily_stats": {
            "avg_load_kw":    round(float(df["total_load_kw"].mean()),3),
            "peak_load_kw":   round(float(df["total_load_kw"].max()),3),
            "accident_count": int((df["accident_type"] != "none").sum()),
            "warn_hours":     int((df["panel_status"] == "warn").sum()),
            "danger_hours":   int((df["panel_status"] == "danger").sum()),
        }
    }
    circuits = {}
    for i in range(1,10):
        circuits[f"c{i}"] = {
            "load_kw":   round(float(last.get(f"c{i}_kw",0)),3),
            "load_rate": round(float(last.get(f"c{i}_rate",0)),3),
            "current_a": round(float(last.get(f"c{i}_current",0)),2),
        }
    summary["circuits"] = circuits
    success_json = github_push_file(
        content_str=json.dumps(summary, ensure_ascii=False, indent=2),
        repo_path="data/latest_summary.json",
        commit_msg=f"[시뮬레이터] {date_str} 요약 업데이트",
        token=token, repo=repo,
    )
    if success_csv and success_json:
        print(f"[GitHub] push 완료 — {summary['total_load_kw']}kW / {summary['panel_status']}")
        return True
    return False

def fetch_simulation_data(token=None, repo=None):
    token = token or GITHUB_TOKEN
    repo  = repo  or GITHUB_REPO
    print("[데이터 수신] GitHub에서 읽는 중...")
    csv_content  = github_get_file("data/panel_simulation.csv", token, repo)
    json_content = github_get_file("data/latest_summary.json",  token, repo)
    if csv_content is None:
        print("[데이터 수신] CSV 없음 — 시뮬레이터 먼저 실행 필요")
        return None, None
    df      = pd.read_csv(io.StringIO(csv_content))
    summary = json.loads(json_content) if json_content else {}
    print(f"[데이터 수신] 완료: {len(df)}행 / {summary.get('updated_at','?')}")
    return df, summary


# ── ASOS 10년 기후 캐시 관리 ──────────────────────────

ASOS_STN_ID   = 235
ASOS_BASE_URL = "http://apis.data.go.kr/1360000/AsosDalyInfoService/getWthrDataList"
ASOS_CACHE_PATH = "data/asos_climate.json"
ASOS_YEARS    = 10

def _fetch_one_year_asos(api_key, year, stn_id=ASOS_STN_ID):
    """ASOS API로 1년치 일자료 수집 → {m-d: {avg_temp, max_temp, ...}} 반환"""
    params = {
        "serviceKey": api_key, "numOfRows": 400, "pageNo": 1,
        "dataType": "JSON", "dataCd": "ASOS", "dateCd": "DAY",
        "startDt": f"{year}0101", "endDt": f"{year}1231", "stnIds": stn_id,
    }
    for attempt in range(2):
        try:
            resp = requests.get(ASOS_BASE_URL, params=params, timeout=30)
            data = resp.json()
            code = data.get("response",{}).get("header",{}).get("resultCode","")
            if code != "00":
                print(f"  [ASOS] {year}년 오류 {code}")
                return {}
            items = data["response"]["body"]["items"].get("item", [])
            if isinstance(items, dict): items = [items]
            result = {}
            for item in items:
                dt_str = str(item.get("tm","")).replace("-","")
                if len(dt_str) < 8: continue
                m, d = int(dt_str[4:6]), int(dt_str[6:8])
                key  = f"{m}-{d}"
                try:
                    avg = item.get("avgTa"); mx = item.get("maxTa")
                    mn  = item.get("minTa"); reh = item.get("avgRhm")
                    result[key] = {
                        "avg_temp": float(avg) if avg not in (None,"") else None,
                        "max_temp": float(mx)  if mx  not in (None,"") else None,
                        "min_temp": float(mn)  if mn  not in (None,"") else None,
                        "avg_reh":  float(reh) if reh not in (None,"") else None,
                    }
                except: continue
            print(f"  [ASOS] {year}년 완료 ({len(result)}일)")
            return result
        except Exception as e:
            print(f"  [ASOS] {year}년 {'재시도' if attempt else '요청'} 실패: {e}")
            if attempt == 0: time.sleep(3)
    return {}

def _merge_asos_years(year_data_list):
    """여러 연도 데이터 → 월-일 평균값 계산"""
    records = defaultdict(lambda: {"temps":[],"maxs":[],"mins":[],"rehs":[]})
    for year_data in year_data_list:
        for key, v in year_data.items():
            if v.get("avg_temp") is not None: records[key]["temps"].append(v["avg_temp"])
            if v.get("max_temp") is not None: records[key]["maxs"].append(v["max_temp"])
            if v.get("min_temp") is not None: records[key]["mins"].append(v["min_temp"])
            if v.get("avg_reh")  is not None: records[key]["rehs"].append(v["avg_reh"])
    result = {}
    for key, v in records.items():
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
    return result

def load_asos_cache(token=None, repo=None):
    """
    GitHub에서 asos_climate.json 읽기
    없으면 None 반환
    """
    token = token or GITHUB_TOKEN
    repo  = repo  or GITHUB_REPO
    content = github_get_file(ASOS_CACHE_PATH, token, repo)
    if content is None:
        return None
    try:
        return json.loads(content)
    except:
        return None

def save_asos_cache(cache_obj, token=None, repo=None):
    """asos_climate.json을 GitHub에 저장"""
    token = token or GITHUB_TOKEN
    repo  = repo  or GITHUB_REPO
    return github_push_file(
        content_str=json.dumps(cache_obj, ensure_ascii=False, indent=2),
        repo_path=ASOS_CACHE_PATH,
        commit_msg=f"[ASOS] 기후 캐시 업데이트 {datetime.now().strftime('%Y-%m-%d')}",
        token=token, repo=repo,
    )

def build_asos_cache_full(api_key, token=None, repo=None):
    """
    최초 1회 실행 — 10년치 전체 수집 후 GitHub에 저장
    구조: {
        "last_updated": "2026-04-22",
        "years": 10,
        "year_data": {"2016": {"4-1": {...}, ...}, ...},
        "avg_data":  {"4-1": {...}, ...}   ← 평균값
    }
    """
    now        = datetime.now()
    end_year   = now.year - 1
    start_year = end_year - ASOS_YEARS + 1
    print(f"[ASOS] 최초 수집 시작: {start_year}~{end_year}년")

    year_data = {}
    for year in range(start_year, end_year+1):
        year_data[str(year)] = _fetch_one_year_asos(api_key, year)

    avg_data = _merge_asos_years(list(year_data.values()))

    cache_obj = {
        "last_updated": now.strftime("%Y-%m-%d"),
        "years":        ASOS_YEARS,
        "end_year":     end_year,
        "year_data":    year_data,
        "avg_data":     avg_data,
    }
    save_asos_cache(cache_obj, token, repo)
    print(f"[ASOS] 캐시 저장 완료 — {len(avg_data)}개 날짜")
    return cache_obj

def update_asos_cache_daily(api_key, token=None, repo=None):
    """
    매일 자정 실행 — 어제 하루치만 추가, 가장 오래된 하루 삭제
    10년 윈도우 유지
    """
    token = token or GITHUB_TOKEN
    repo  = repo  or GITHUB_REPO

    # 캐시 읽기
    cache = load_asos_cache(token, repo)
    if cache is None:
        print("[ASOS] 캐시 없음 → 최초 전체 수집 시작")
        from src.config import KMA_API_KEY
        return build_asos_cache_full(api_key, token, repo)

    now      = datetime.now()
    today    = now.date()
    yesterday = today - timedelta(days=1)

    # 이미 오늘 업데이트했으면 스킵
    if cache.get("last_updated") == str(today):
        print(f"[ASOS] 오늘 이미 업데이트됨 ({today})")
        return cache

    end_year   = cache.get("end_year", now.year-1)
    start_year = end_year - ASOS_YEARS + 1
    year_data  = cache.get("year_data", {})

    # 어제가 새 연도의 시작이면 새 연도 추가 + 가장 오래된 연도 삭제
    new_year = yesterday.year
    if str(new_year) not in year_data and new_year > end_year:
        print(f"[ASOS] 새 연도 {new_year} 추가 수집...")
        year_data[str(new_year)] = _fetch_one_year_asos(api_key, new_year)
        # 가장 오래된 연도 삭제
        old_year = str(start_year)
        if old_year in year_data:
            del year_data[old_year]
            print(f"[ASOS] {old_year}년 데이터 삭제 (10년 윈도우 유지)")
        end_year   = new_year
        start_year = end_year - ASOS_YEARS + 1

    # 평균 재계산
    avg_data = _merge_asos_years(list(year_data.values()))

    cache_obj = {
        "last_updated": str(today),
        "years":        ASOS_YEARS,
        "end_year":     end_year,
        "year_data":    year_data,
        "avg_data":     avg_data,
    }
    save_asos_cache(cache_obj, token, repo)
    print(f"[ASOS] 일별 업데이트 완료 — {len(avg_data)}개 날짜")
    return cache_obj

def get_asos_avg_data(api_key, token=None, repo=None):
    """
    avg_data 반환 (캐시 우선, 없으면 전체 수집)
    calendar_builder에서 호출
    """
    cache = load_asos_cache(token, repo)
    if cache and "avg_data" in cache:
        print(f"[ASOS] 캐시 사용 (최종 업데이트: {cache.get('last_updated','?')})")
        return cache["avg_data"]
    print("[ASOS] 캐시 없음 → 최초 전체 수집")
    cache = build_asos_cache_full(api_key, token, repo)
    return cache.get("avg_data", {})
