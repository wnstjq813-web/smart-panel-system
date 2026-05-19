"""
run_simulator.py — 시뮬레이터 실행 진입점
수정: 자동 실행(cron)일 때 forced_accident/event 초기화 → 기본 확률로 동작
"""
import json, os
from src.config import CITY, EQUIPMENT_AGE, KMA_API_KEY, GITHUB_TOKEN, now_kst
from src.kma_weather import get_grid, get_today_weather
from src.simulator import simulate_day
from src.github_utils import push_staged_csv, DATA_REPO

def load_config():
    config_path = "config/config.json"
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def main():
    now = now_kst()
    print(f"\n{'='*55}")
    print(f" 시뮬레이터 실행: {now.strftime('%Y-%m-%d %H:%M:%S')} KST")
    print(f"{'='*55}")

    cfg          = load_config()
    city         = cfg.get("city",           CITY)
    equip_age    = cfg.get("equipment_age",  EQUIPMENT_AGE)
    triggered_by = cfg.get("triggered_by",   "auto")

    # ── 실행 방식에 따른 파라미터 결정 ───────────────
    if triggered_by == "streamlit":
        # 수동 실행 — Streamlit 설정값 그대로 사용
        forced_acc   = cfg.get("forced_accident", "none")
        forced_event = cfg.get("special_event",   "auto")
        print(f" 실행 방식: 🖱️ 수동 (Streamlit)")
        print(f" 강제 사고: {forced_acc} | 이벤트: {forced_event}")
    else:
        # 자동 실행 (cron) — 강제 설정 무시, 기본 확률로 동작
        forced_acc   = "none"
        forced_event = "auto"
        print(f" 실행 방식: ⏰ 자동 (cron)")
        print(f" 강제 사고/이벤트 초기화 → 기본 확률 적용")

    print(f" 설정: 도시={city} | 설비노후={equip_age}년")

    # 날씨 수집
    print("\n[1/3] KMA 날씨 수집 중...")
    NX, NY        = get_grid(city)
    today_weather = get_today_weather(nx=NX, ny=NY, api_key=KMA_API_KEY)
    print(f"  날씨: {today_weather['temperature']}°C / "
          f"{today_weather['humidity']}% / {today_weather['weather_code']}")

    # 시뮬레이션
    print("\n[2/3] 시뮬레이션 실행 중 → panel_staged.csv...")
    rows = simulate_day(
        date                = now,
        weather_data        = today_weather,
        equipment_age_years = equip_age,
        output_csv          = "panel_staged.csv",
        forced_accident     = forced_acc,
        forced_event        = forced_event,
    )
    print(f"  완료: {len(rows)}행 생성")

    # GitHub push
    print("\n[3/3] GitHub push 중 (staged)...")
    ok = push_staged_csv(csv_path="panel_staged.csv", token=GITHUB_TOKEN, repo=DATA_REPO)
    print(f"  GitHub push: {'✅ 완료' if ok else '❌ 실패'}")
    print(f"\n{'='*55}\n ✅ 시뮬레이터 완료\n{'='*55}")

if __name__ == "__main__":
    main()
