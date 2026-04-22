"""
github_utils.py — GitHub 데이터 송수신 모듈 (STEP 8·9)
"""
import requests, base64, json, io
import pandas as pd
from datetime import datetime
from src.config import GITHUB_TOKEN, GITHUB_REPO

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
        print(f"  [GitHub] {csv_path} 파일 없음 — 시뮬레이션 먼저 실행 필요")
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
        print(f"[GitHub] push 완료 — 총 부하: {summary['total_load_kw']}kW / 상태: {summary['panel_status']}")
        return True
    return False

def fetch_simulation_data(token=None, repo=None):
    token = token or GITHUB_TOKEN
    repo  = repo  or GITHUB_REPO
    print("[데이터 수신] GitHub에서 읽는 중...")
    csv_content  = github_get_file("data/panel_simulation.csv",  token, repo)
    json_content = github_get_file("data/latest_summary.json",   token, repo)
    if csv_content is None:
        print("[데이터 수신] CSV 없음 — 시뮬레이터 먼저 실행 필요")
        return None, None
    df      = pd.read_csv(io.StringIO(csv_content))
    summary = json.loads(json_content) if json_content else {}
    print(f"[데이터 수신] 완료: {len(df)}행")
    print(f"  최신 업데이트: {summary.get('updated_at','알 수 없음')}")
    print(f"  현재 부하: {summary.get('total_load_kw',0)}kW / 상태: {summary.get('panel_status','-')}")
    return df, summary
