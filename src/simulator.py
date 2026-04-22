"""
simulator.py — 시뮬레이션 실행 함수 (STEP 7)
"""
import os, csv, random
from datetime import datetime
from src.config import CIRCUITS, EQUIPMENT_AGE, KMA_API_KEY, KAKAO_API_KEY
from src.kma_weather import get_weather_for_hour
from src.lightning import fetch_lightning, get_lightning_multiplier, summarize_lightning
from src.panel_config import calc_accident_probs
from src.llm_simulator import build_prompt, call_llm, apply_physics

def get_time_slot(hour):
    if   hour < 7:  return "night"
    elif hour < 9:  return "commute"
    elif hour < 12: return "work_am"
    elif hour < 13: return "lunch"
    elif hour < 18: return "work_pm"
    elif hour < 22: return "evening"
    else:           return "night"

def get_season(month):
    if   month in [3,4,5]:   return "spring"
    elif month in [6,7,8]:   return "summer"
    elif month in [9,10,11]: return "autumn"
    else:                    return "winter"

def get_occupancy(slot, day_type):
    if day_type in ["weekend","holiday"]: return round(random.uniform(0.0,0.05),2)
    base = {"night":0.00,"commute":0.40,"work_am":0.85,"lunch":0.50,"work_pm":0.90,"evening":0.20}
    return round(max(0.0, min(1.0, base.get(slot,0.5) + random.uniform(-0.08,0.08))),2)

def get_special_event(slot, day_type):
    if day_type in ["weekend","holiday"] or slot=="night": return "none"
    pool = ["none"]*14 + ["overtime"]*2 + ["visitor"]*2 + ["meeting"]*1 + ["construction"]*1
    return random.choice(pool)

def get_circuit_states(slot):
    if slot=="night":                       return [0,1,0,0,0,1,0,1,0]
    elif slot in ["commute","evening"]:     return [1,1,1,1,1,1,0,1,0]
    else:                                   return [1,1,1,1,1,1,1,1,0]

def save_to_csv(rows, filepath):
    if not rows: return
    file_exists = os.path.exists(filepath)
    mode = "a" if file_exists else "w"
    with open(filepath, mode, newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        if not file_exists: writer.writeheader()
        writer.writerows(rows)
    print(f"CSV 저장 완료 → {filepath} ({len(rows)}행 추가)")

def simulate_day(date, weather_data, equipment_age_years=EQUIPMENT_AGE, output_csv="panel_simulation.csv"):
    day_type = "weekend" if date.weekday() >= 5 else "weekday"
    season   = get_season(date.month)
    rows     = []
    recent_accidents = []
    prev_load_kw     = 0.0

    print(f"\n{'='*55}")
    print(f" 시뮬레이션: {date.strftime('%Y-%m-%d')} ({day_type}) | 설비 {equipment_age_years}년")
    print(f" 날씨: {weather_data['temperature']}°C / {weather_data['humidity']}% / {weather_data['weather_code']}")
    print(f"{'='*55}")

    for hour in range(24):
        dt   = date.replace(hour=hour, minute=0, second=0, microsecond=0)
        slot = get_time_slot(hour)
        hw   = get_weather_for_hour(weather_data, hour)

        lgt_data    = fetch_lightning(kma_key=KMA_API_KEY, kakao_key=KAKAO_API_KEY, now=dt)
        lgt_summary = summarize_lightning(lgt_data)
        lgt_mult    = get_lightning_multiplier(lgt_data)

        ctx = {
            "temperature":         hw.get("temperature", weather_data["temperature"]),
            "humidity":            hw.get("humidity",    weather_data["humidity"]),
            "weather_code":        hw.get("weather_code",weather_data["weather_code"]),
            "season":              season,
            "is_thunder":          lgt_summary["detected"],
            "datetime":            dt.isoformat(),
            "day_type":            day_type,
            "time_slot":           slot,
            "hour":                hour,
            "occupancy_rate":      get_occupancy(slot, day_type),
            "special_event":       get_special_event(slot, day_type),
            "equipment_age_years": equipment_age_years,
            "prev_load_kw":        round(prev_load_kw, 2),
            "circuit_states":      get_circuit_states(slot),
            "recent_accidents":    recent_accidents[-3:],
            "lgt_multiplier":      lgt_mult,
            "lgt_data":            lgt_summary,
        }

        probs   = calc_accident_probs(ctx)
        prompt  = build_prompt(ctx, probs)
        llm_out = call_llm(prompt)
        result  = apply_physics(llm_out)

        if result.get("accident"):
            recent_accidents.append(result["accident"]["type"])
        prev_load_kw = result["total_load_kw"]

        accident = result.get("accident") or {}
        row = {
            "datetime":           dt.isoformat(),
            "temperature":        ctx["temperature"],
            "humidity":           ctx["humidity"],
            "weather_code":       ctx["weather_code"],
            "season":             season,
            "is_thunder":         int(ctx["is_thunder"]),
            "day_type":           day_type,
            "time_slot":          slot,
            "occupancy_rate":     ctx["occupancy_rate"],
            "special_event":      ctx["special_event"],
            "total_load_kw":      result["total_load_kw"],
            "total_current_a":    result["total_current_a"],
            "supply_voltage_v":   result["supply_voltage_v"],
            "panel_status":       result["panel_status"],
            "accident_type":      result.get("accident_type", "none"),
            "accident_circuit":   result.get("accident_circuit", "none"),
            "accident_severity":  result.get("accident_severity", "none"),
            "current_multiplier": accident.get("current_multiplier", 1.0),
            "voltage_delta_v":    accident.get("voltage_delta_v", 0.0),
            "duration_min":       accident.get("duration_min", 0),
            "trip_expected":      int(accident.get("trip_expected", False)),
            "lgt_detected":       int(lgt_summary["detected"]),
            "lgt_danger_level":   lgt_summary["danger_level"],
            "lgt_count_10min":    lgt_summary["count_10min"],
            "lgt_dist_km":        lgt_summary["closest_dist_km"] or 0,
            "lgt_type":           lgt_summary["closest_type"] or "none",
            "lgt_amp_ka":         lgt_summary["closest_amp_ka"] or 0,
            "lgt_address":        lgt_summary["closest_address"] or "",
        }
        for cid, c in result["circuits"].items():
            row[f"{cid}_rate"]    = c["load_rate"]
            row[f"{cid}_kw"]      = c["load_kw"]
            row[f"{cid}_current"] = c["current_a"]
        rows.append(row)

        acc_str = result.get("accident_type", "-")
        print(f"  [{dt.strftime('%H:%M')}] "
              f"{result['total_load_kw']:5.2f}kW | "
              f"{result['total_current_a']:5.1f}A | "
              f"{result['supply_voltage_v']:.0f}V | "
              f"[{result['panel_status']:6}] | "
              f"사고: {acc_str}")

    save_to_csv(rows, output_csv)
    return rows
