"""
llm_simulator.py — Claude API 호출 및 물리 검증 (STEP 6)
"""
import anthropic, json, random, httpx
from src.config import ANTHROPIC_API_KEY, PANEL_CONFIG, CIRCUITS

SYSTEM_PROMPT = """당신은 스마트 분전반 전력 시뮬레이터입니다.
입력된 컨텍스트(날씨, 시간대, 이벤트, 사고확률)를 바탕으로
9개 회로의 전력 부하와 사고 여부를 JSON으로 출력하세요.

출력 형식 (반드시 JSON만, 설명 없이):
{
  "circuits": {
    "c1": {"load_kw": 0.5},
    "c2": {"load_kw": 0.3},
    "c3": {"load_kw": 1.2},
    "c4": {"load_kw": 0.8},
    "c5": {"load_kw": 2.1},
    "c6": {"load_kw": 0.9},
    "c7": {"load_kw": 0.4},
    "c8": {"load_kw": 1.5},
    "c9": {"load_kw": 0.0}
  },
  "accident_type": "none",
  "accident_severity": "none",
  "accident_circuit": "none"
}

accident_type 가능값: none, overcurrent, earth_fault, voltage_abnormality,
motor_lock, lightning_surge, overvoltage, insulation_degradation,
contact_failure, harmonic_distortion, low_power_factor,
phase_unbalance, capacitor_failure, aging_failure, arc_fault

accident_severity 가능값: none, info, warn, critical"""

def build_prompt(ctx, probs):
    top      = sorted(probs.items(), key=lambda x: x[1], reverse=True)[:5]
    prob_str = "\n".join([f"  - {k}: {v*100:.1f}%" for k, v in top])
    return (f"현재 상황:\n"
            f"- 날씨: {ctx['temperature']}°C / 습도 {ctx['humidity']}% / {ctx['weather_code']}\n"
            f"- 시간대: {ctx['time_slot']} ({ctx['hour']}시) / {ctx['day_type']}\n"
            f"- 계절: {ctx['season']}\n"
            f"- 특수이벤트: {ctx['special_event']}\n"
            f"- 재실률: {ctx['occupancy_rate']*100:.0f}%\n"
            f"- 설비노후: {ctx['equipment_age_years']}년\n"
            f"- 낙뢰: {'감지됨' if ctx.get('is_thunder') else '없음'}\n\n"
            f"사고 발생 확률 상위 5개:\n{prob_str}\n\n"
            f"위 조건에 맞는 9개 회로 전력 부하(kW)와 사고 여부를 JSON으로 출력하세요.")

def _fallback_output():
    return {"circuits":{f"c{i}":{"load_kw":round(random.uniform(0.1,1.0),3)} for i in range(1,10)},
            "accident_type":"none","accident_severity":"none","accident_circuit":"none"}

def call_llm(prompt):
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY,
                                     http_client=httpx.Client(timeout=60.0))
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role":"user","content":prompt}]
        )
        raw = msg.content[0].text.strip()
        if "```" in raw:
            for part in raw.split("```"):
                p = part.strip().lstrip("json").strip()
                if p.startswith("{"): raw = p; break
        return json.loads(raw)
    except Exception as e:
        print(f"[경고] LLM 호출 실패: {e} → 기본값 사용")
        return _fallback_output()

def apply_physics(llm_out, voltage=220.0):
    circuits  = llm_out.get("circuits", {})
    result    = {}
    total_kw  = 0.0
    for cid, cdata in circuits.items():
        kw      = max(0.0, float(cdata.get("load_kw", 0)))
        rated   = CIRCUITS.get(cid, {}).get("rated_kw", 1.0)
        kw      = min(kw, rated * 1.2)
        current = round(kw * 1000 / voltage, 2)
        rate    = round(kw / rated, 3) if rated > 0 else 0
        result[cid] = {"load_kw":round(kw,3),"current_a":current,"load_rate":rate}
        total_kw += kw
    llm_out["circuits"]        = result
    llm_out["total_load_kw"]   = round(total_kw, 3)
    llm_out["total_current_a"] = round(total_kw * 1000 / voltage, 2)
    llm_out["supply_voltage_v"]= round(voltage, 1)
    warn_kw   = PANEL_CONFIG["main_capacity_kw"] * PANEL_CONFIG["warn_threshold"]
    danger_kw = PANEL_CONFIG["main_capacity_kw"] * PANEL_CONFIG["danger_threshold"]
    llm_out["panel_status"] = ("danger" if total_kw >= danger_kw
                               else "warn" if total_kw >= warn_kw else "normal")
    return llm_out
