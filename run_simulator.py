"""
run_simulator.py — 시뮬레이터 실행 진입점
GitHub Actions: config/config.json 변경 시 자동 실행
"""
import json, os
from datetime import datetime
from src.config import CITY, EQUIPMENT_AGE, KMA_API_KEY, GITHUB_TOKEN, GITHUB_REPO
from src.kma_weather import get_grid, get_today_weather
from src.simulator import simulate_day
from src.github_utils import push_simulation_results

def load_config():
    """Streamlit이 기록한 config.json 읽기"""
    config_path = "config/config.json"
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def main():
    now = datetime.now()
    print(f"\n{'='*55}")
    print(f" 시뮬레이터 실행: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*55}")

    # config.json에서 파라미터 읽기 (Streamlit UI 설정값)
    cfg           = load_config()
    city          = cfg.get("city", CITY)
    equipment_age = cfg.get("equipment_age", EQUIPMENT_AGE)
    print(f" 설정: 도시={city} | 설비노후={equipment_age}년")

    # 날씨 수집
    print("\n[1/3] KMA 날씨 수집 중...")
    NX, NY        = get_grid(city)
    today_weather = get_today_weather(nx=NX, ny=NY, api_key=KMA_API_KEY)
    print(f"  날씨: {today_weather['temperature']}°C / {today_weather['humidity']}% / {today_weather['weather_code']}")

    # 시뮬레이션 실행
    print("\n[2/3] 시뮬레이션 실행 중...")
    output_csv = "panel_simulation.csv"
    rows = simulate_day(
        date=now,
        weather_data=today_weather,
        equipment_age_years=equipment_age,
        output_csv=output_csv,
    )
    print(f"  완료: {len(rows)}행 생성")

    # GitHub push
    print("\n[3/3] GitHub push 중...")
    ok = push_simulation_results(csv_path=output_csv, token=GITHUB_TOKEN, repo=GITHUB_REPO)
    print(f"  GitHub push: {'✅ 완료' if ok else '❌ 실패'}")

    print(f"\n{'='*55}")
    print(f" ✅ 시뮬레이터 완료")
    print(f"{'='*55}")

if __name__ == "__main__":
    main()
