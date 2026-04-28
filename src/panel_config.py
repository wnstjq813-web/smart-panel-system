"""
panel_config.py — 사고 확률 계산 모듈
수정: forced_accident 시 해당 사고 확률 0.99로 강제 설정
"""
from src.config import PANEL_CONFIG, CIRCUITS

# panel_config 키 → accident_type 매핑
PROB_TO_ACCIDENT = {
    "overload":              "overcurrent",
    "short_circuit":         "earth_fault",
    "earth_fault":           "earth_fault",
    "insulation_degradation":"insulation_degradation",
    "overvoltage":           "overvoltage",
    "undervoltage":          "voltage_abnormality",
    "motor_starting":        "motor_lock",
    "motor_locked":          "motor_lock",
    "low_power_factor":      "low_power_factor",
    "lightning_surge":       "lightning_surge",
    "power_restoration":     "voltage_abnormality",
    "harmonic_distortion":   "harmonic_distortion",
    "contact_heating":       "contact_failure",
    "cb_aging_trip":         "cb_aging_trip",
    "intermittent_open":     "contact_failure",
}

def calc_accident_probs(ctx):
    temp     = ctx["temperature"]
    humidity = ctx["humidity"]
    age      = ctx["equipment_age_years"]
    thunder  = ctx["is_thunder"]
    event    = ctx["special_event"]
    slot     = ctx["time_slot"]
    lgt_mult = ctx.get("lgt_multiplier", 1.0)
    forced   = ctx.get("forced_accident", "none")  # 강제 사고 지정

    def cap(p, limit=0.15): return min(round(p, 6), limit)
    probs = {}

    p = 0.020
    if temp>30: p*=1.8
    if temp>35: p*=1.4
    if event=="overtime":     p*=1.6
    if event=="visitor":      p*=1.4
    if event=="meeting":      p*=1.3
    if event=="construction": p*=1.2
    if slot=="night":         p*=0.2
    probs["overload"] = cap(p)

    p = 0.003
    if event=="visitor":      p*=2.0
    if event=="construction": p*=3.0
    if age>=10: p*=2.5
    if slot=="night": p*=0.3
    probs["short_circuit"] = cap(p)

    p = 0.008
    if humidity>80: p*=2.5
    if humidity>90: p*=1.6
    if age>=7:  p*=1.8
    if age>=10: p*=1.7
    if event=="construction": p*=2.0
    probs["earth_fault"] = cap(p)

    p = 0.015
    if age>=7:  p*=2.0
    if age>=12: p*=2.0
    if humidity>75: p*=1.5
    if slot=="night": p*=0.8
    probs["insulation_degradation"] = cap(p)

    p = 0.005
    if thunder: p *= (lgt_mult / 5)
    if temp>35: p*=1.3
    probs["overvoltage"] = cap(p)

    p = 0.008
    if temp>35:         p*=2.0
    if slot=="commute": p*=1.5
    if slot=="night":   p*=0.3
    probs["undervoltage"] = cap(p)

    p = 0.008
    if slot == "commute": p *= 2.0
    if slot == "night":   p *= 0.0
    if slot in ["work_am","work_pm","lunch","evening"]: p *= 0.3
    if "motor_lock" in ctx.get("recent_accidents", []): p *= 0.05
    probs["motor_starting"] = cap(p)

    p = 0.003
    if age>=8:  p*=3.0
    if age>=12: p*=1.7
    if temp<-5: p*=2.0
    probs["motor_locked"] = cap(p)

    p = 0.010
    if age>=8:  p*=2.5
    if temp>30: p*=1.4
    probs["low_power_factor"] = cap(p)

    p = 0.001
    p *= lgt_mult
    probs["lightning_surge"] = cap(p, 0.25)

    p = 0.002
    if thunder: p*=5.0
    if temp>35: p*=2.0
    probs["power_restoration"] = cap(p)

    p = 0.020
    if slot in ["work_am","work_pm"]: p*=1.5
    if temp>30: p*=1.4
    if slot=="night": p*=0.5
    probs["harmonic_distortion"] = cap(p)

    p = 0.010
    if age>=8:  p*=2.0
    if age>=12: p*=2.5
    if temp>30: p*=1.5
    probs["contact_heating"] = cap(p)

    p = 0.005
    if age>=10: p*=4.0
    if age>=15: p*=2.0
    if temp>35: p*=1.5
    probs["cb_aging_trip"] = cap(p)

    p = 0.008
    if age>=7:  p*=2.0
    if event=="construction": p*=3.0
    probs["intermittent_open"] = cap(p)

    # [수정] forced_accident 처리 — 해당 사고 키 확률을 0.99로 강제
    if forced and forced != "none":
        for prob_key, acc_type in PROB_TO_ACCIDENT.items():
            if acc_type == forced:
                probs[prob_key] = 0.99
        # 직접 매핑이 없는 경우 (arc_fault 등) — 가장 유사한 키에 적용
        if forced == "arc_fault":
            probs["contact_heating"]   = 0.99
            probs["insulation_degradation"] = 0.70
        elif forced == "phase_unbalance":
            probs["motor_locked"]      = 0.99
        print(f"[사고확률] '{forced}' 강제 지정 → 관련 확률 0.99 설정")

    return probs
