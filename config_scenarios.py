"""Private simulation fixtures. Only public_profile/catalog are inference context.

Values and provenance follow the supplied 2026-11-14 engineering specification.
Clinical pending items are deliberately not auto-filled.
"""
from copy import deepcopy
from pathlib import Path
import json

EXAMS = {
    "blood_pressure": {"label": "Blood pressure", "unit": "mmHg"},
    "temperature": {"label": "Temperature", "unit": "°C"},
    "respiratory_rate": {"label": "Respiratory rate", "unit": "/min"},
    "pulse": {"label": "Heart rate", "unit": "bpm"},
    "spo2": {"label": "SpO₂", "unit": "%"},
    "abdomen": {"label": "Abdominal examination", "unit": "description"},
    "skin": {"label": "Skin / conjunctivae", "unit": "description"},
    "capillary_refill": {"label": "Capillary refill", "unit": "s"},
    "airway": {"label": "A · Speech and airway signs", "unit": "description"},
    "breathing_work": {"label": "B · Breathing effort", "unit": "description"},
    "circulation": {"label": "C · Circulatory signs", "unit": "description"},
}

SCENARIOS = {
    "N02": {
        "title": "Lightheadedness and gastrointestinal findings", "delay_seconds": 900,
        "public_profile": {"patient_id": "CM-4", "age": 38, "sex": "Female", "role": "Mission specialist",
            "mission_day": 210, "history": ["Right knee overuse, mission day 198"],
            "allergies": "No known drug allergies recorded", "regular_medications": "Not documented",
            "historical_baselines": {"pulse": 64, "blood_pressure": "116/74", "spo2": 98, "temperature": 36.5}, "provenance": "[B]"},
        "opening": "I've felt very lightheaded and weak since yesterday.",
        "exam_ids": ["blood_pressure", "temperature", "respiratory_rate", "pulse", "spo2", "abdomen", "skin", "capillary_refill"],
        "private_exams": {"blood_pressure": ("108/70", "[G]"), "temperature": (36.5, "[A]"),
            "respiratory_rate": (18, "[A]"), "abdomen": ("Soft abdomen; mild epigastric tenderness", "[A]"),
            "skin": ("Conjunctival pallor", "[A]"), "capillary_refill": ("~3", "[A]")},
        "hidden_truth": "Possible upper gastrointestinal bleeding associated with ibuprofen; hidden hypothesis, not a confirmed diagnosis.",
        "actor_notes": "Only when asked: dark stools since yesterday, almost black, sticky and strong-smelling; two episodes; no visible red blood or vomiting blood; ibuprofen a couple of times this week. No other complete verbatim answers were supplied.",
        "pending": ["Initial safety checks are entered by the operator; no default answers.", "The script is inconsistent about standing in microgravity; orthostatic blood pressure is not offered."],
        "schedule": [],
    },
    "N04": {
        "title": "Rash and respiratory deterioration", "delay_seconds": 1320,
        "public_profile": {"patient_id": "CM-5", "age": 35, "sex": "Female", "role": "Mission specialist",
            "mission_day": 60, "history": [], "allergies": "No known drug or food allergies recorded",
            "regular_medications": "Not documented", "historical_baselines": {"pulse": 70, "blood_pressure": "110/70", "spo2": 99, "temperature": 36.7}, "provenance": "[B]"},
        "opening": "I've developed an itchy rash on my arms and chest. It started about ten minutes ago.",
        "exam_ids": ["blood_pressure", "respiratory_rate", "skin", "capillary_refill", "pulse", "spo2", "temperature", "airway", "breathing_work", "circulation"],
        "private_exams": {"blood_pressure": ("118/74", "[B]"), "respiratory_rate": (18, "[B]"),
            "temperature": (36.8, "[B]"), "skin": ("Urticarial rash", "[B]"), "capillary_refill": ("<2", "[B]")},
        "private_late_exams": {"blood_pressure": ("90/58", "[G]"), "respiratory_rate": (26, "[B]"),
            "skin": ("More extensive urticarial rash", "[B]/[D]"), "capillary_refill": ("3–4", "[B]")},
        "hidden_truth": "Progressive reaction possibly associated with a new food; no confirmed diagnosis [D].",
        "actor_notes": "The breathing difficulty statement appears only when the T+2 event occurs. The operator enters any additional responses.",
        "pending": ["Manual initial safety checks.", "Illustrative A/B/C fields require clinical review; they do not include treatments."],
        "schedule": [{"id": "deterioration", "at": 120, "type": "critical_event",
            "payload": {"crew_statement": "My voice is getting hoarse, and I'm starting to have trouble breathing. It feels like my throat is tightening."}}],
    },
    "N06": {
        "title": "Fever and communication outage", "delay_seconds": 900,
        "public_profile": {"patient_id": "CM-6", "age": 40, "sex": "Male", "role": "Flight engineer",
            "mission_day": 250, "history": [], "allergies": "No known drug allergies recorded",
            "regular_medications": "No regular medication recorded", "historical_baselines": {"pulse": 66, "blood_pressure": "120/78", "spo2": 98, "temperature": 36.6}, "provenance": "[B]"},
        "opening": "I've been feeling feverish and unusually tired since yesterday. I think I'm getting worse.",
        "exam_ids": ["blood_pressure", "temperature", "respiratory_rate", "pulse", "spo2"],
        "private_exams": {"blood_pressure": ("124/78", "[B]"), "respiratory_rate": (18, "[B]")},
        "private_late_exams": {"blood_pressure": ("104/68", "[G]"), "respiratory_rate": (20, "[B]")},
        "hidden_truth": "No established diagnosis; do not assign a specific infectious cause.",
        "actor_notes": "If asked about initial temperature: 38.4 °C reported about 10 minutes earlier; record as crew_reported, not as a sensor. At T+6 h the event adds the report of 39.1 °C. Thermometer confirmation requires a separate manual entry.",
        "pending": ["A 15-minute delay and T+7 h link recovery are proposed simulation settings [D].", "Manual initial safety checks.", "A reported temperature is not a newly measured examination result."],
        "schedule": [
            {"id": "link_down", "at": 1200, "type": "link_change", "payload": {"status": "DOWN"}},
            {"id": "reassessment", "at": 21600, "type": "reassessment_event", "payload": {"crew_statement": "I feel weaker; I am reporting a temperature of 39.1 °C."}},
            {"id": "link_up", "at": 25200, "type": "link_change", "payload": {"status": "UP"}},
        ],
    },
}


def load_recorded_case(scenario_id: str) -> dict:
    if scenario_id not in ("C01", "C02"):
        raise ValueError("Unknown recorded case.")
    path = Path(__file__).resolve().parent / "case_data" / f"{scenario_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


for _case_id in ("C01", "C02"):
    _case = load_recorded_case(_case_id)
    SCENARIOS[_case_id] = {
        "title": f"Case {_case_id[-1]} · {_case['title']}",
        "delay_seconds": 900,
        "public_profile": {"patient_id": f"SIM-{_case_id}", "mission": "Mars transit",
            "record_status": "No demographics or medical history were supplied in the attachment.",
            "identifier_note": "Technical simulation identifier, not the astronaut's identity."},
        "opening": _case["opening"], "recorded_case": True,
        "exam_ids": ["pulse", "spo2", "blood_pressure", "respiratory_rate", "temperature", "abdomen"],
        "private_exams": {}, "schedule": [], "pending": _case["notes"],
        "actor_notes": "Answers are replayed one at a time from the supplied JSON.",
        "hidden_truth": "No confirmed diagnosis. Model-report hypotheses are not imported.",
    }


def load_scenario(scenario_id: str) -> dict:
    if scenario_id not in SCENARIOS:
        raise ValueError("Unknown scenario.")
    return deepcopy(SCENARIOS[scenario_id])


def exam_catalog(scenario_id: str) -> dict:
    return {key: deepcopy(EXAMS[key]) for key in SCENARIOS[scenario_id]["exam_ids"]}


def telemetry_at(scenario_id: str, seconds: int, *, deteriorated: bool = False) -> dict:
    if scenario_id in ("C01", "C02"):
        return {}  # Empty MEASUREMENTS in the recording: do not fabricate a sensor feed.
    if scenario_id == "N02":
        return {"pulse": round(100 + 8 * min(1, max(0, (seconds + 3600) / 3600)), 1), "spo2": 98}
    if scenario_id == "N04":
        if deteriorated:
            return {"pulse": 124, "spo2": 92}
        return {"pulse": round(72 + 20 * min(1, max(0, (seconds + 900) / 900)), 1), "spo2": 98}
    if scenario_id == "N06":
        fraction = min(1, max(0, seconds / 21600))
        return {"pulse": round(98 + 14 * fraction, 1), "spo2": round(98 - fraction, 1)}
    raise ValueError("Unknown scenario.")


def simulated_exam(scenario_id: str, exam_id: str, seconds: int, *, deteriorated: bool = False):
    """Called only after an exam request. None means no scripted measured result."""
    scenario = load_scenario(scenario_id)
    if scenario.get("recorded_case"):
        return None
    if exam_id not in scenario["exam_ids"]:
        raise ValueError("Examination outside the catalog.")
    if exam_id in ("pulse", "spo2"):
        return telemetry_at(scenario_id, seconds, deteriorated=deteriorated)[exam_id], "[G]/[D]"
    late = deteriorated if scenario_id == "N04" else seconds >= 21600
    if late:
        return scenario.get("private_late_exams", {}).get(exam_id)
    return scenario["private_exams"].get(exam_id)
