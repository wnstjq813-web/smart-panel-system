"""
run_simulator.py — 시뮬레이터 실행 진입점
"""
import json, os
from src.config import CITY, EQUIPMENT_AGE, KMA_API_KEY, GITHUB_TOKEN, now_kst
from src.kma_weather import get_grid, get_today_weather
from src.simulator import simulate_day
from src.github_utils import push_simulation_results, DATA_REPO

def load_config():
    config_path = "config/config.json"
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def main():
    now = now_kst()   # [수정] KST
    print(f"\n{'='*55}")
    print(f" 시뮬레이터 실행: {now.strftime('%Y-%m-%d %H:%M:%S')} KST")
    print(f"{'='*55}")

    cfg           = load_config()
    city          = cfg.get("city",            CITY)
    equipment_age = cfg.get("equipment_age",   EQUIPMENT_AGE)
    forced_acc    = cfg.get("forced_accident", "none")
    forced_event  = cfg.get("special_event",   "auto")

    print(f" 설정: 도시={city} | 설비노후={equipment_age}년 | "
          f"강제사고={forced_acc} | 이벤트={forced_event}")

    print("\n[1/3] KMA 날씨 수집 중...")
    NX, NY        = get_grid(city)
    today_weather = get_today_weather(nx=NX, ny=NY, api_key=KMA_API_KEY)
    print(f"  날씨: {today_weather['temperature']}°C / "
          f"{today_weather['humidity']}% / {today_weather['weather_code']}")

    print("\n[2/3] 시뮬레이션 실행 중...")
    output_csv = "panel_simulation.csv"
    rows = simulate_day(
        date              = now,
        weather_data      = today_weather,
        equipment_age_years = equipment_age,
        output_csv        = output_csv,
        forced_accident   = forced_acc,
        forced_event      = forced_event,
    )
    print(f"  완료: {len(rows)}행 생성")

    print("\n[3/3] GitHub push 중 (기존 데이터 누적)...")
    ok = push_simulation_results(csv_path=output_csv, token=GITHUB_TOKEN, repo=DATA_REPO)
    print(f"  GitHub push: {'✅ 완료' if ok else '❌ 실패'}")
    print(f"\n{'='*55}\n ✅ 시뮬레이터 완료\n{'='*55}")

if __name__ == "__main__":
    main()
