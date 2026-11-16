"""The four supplied recorded cases; no retired scenario fixtures or live sensors."""
from copy import deepcopy
from pathlib import Path
import json

RECORDED_CASE_IDS = ("C01", "C02", "C03", "C04")

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


def load_recorded_case(scenario_id: str) -> dict:
    if scenario_id not in RECORDED_CASE_IDS:
        raise ValueError("Unknown case. Choose one of the four recorded cases.")
    path = Path(__file__).resolve().parent / "case_data" / f"{scenario_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


SCENARIOS = {}
for _case_id in RECORDED_CASE_IDS:
    _case = load_recorded_case(_case_id)
    SCENARIOS[_case_id] = {
        "title": f"Case {int(_case_id[1:])} · {_case['title']}",
        "delay_seconds": 900,
        "public_profile": {"patient_id": f"SIM-{_case_id}",
            "mission": _case["original_context"]["MISSION_CONTEXT"],
            "record_status": "No demographics or medical history were supplied in the attachment context. See the recorded interview for reported history.",
            "identifier_note": "Technical simulation identifier, not the astronaut's identity."},
        "opening": _case["opening"], "recorded_case": True,
        "exam_ids": ["pulse", "spo2", "blood_pressure", "respiratory_rate", "temperature"]
                    + (["abdomen"] if _case_id != "C04" else []),
        "schedule": [], "pending": _case["notes"],
        "actor_notes": "Answers are replayed one at a time from the supplied JSON.",
    }


def load_scenario(scenario_id: str) -> dict:
    if scenario_id not in SCENARIOS:
        raise ValueError("Unknown case. Choose one of the four recorded cases.")
    return deepcopy(SCENARIOS[scenario_id])


def exam_catalog(scenario_id: str) -> dict:
    return {key: deepcopy(EXAMS[key]) for key in SCENARIOS[scenario_id]["exam_ids"]}


def telemetry_at(scenario_id: str, seconds: int, *, deteriorated: bool = False) -> dict:
    load_scenario(scenario_id)
    return {}  # No continuous sensor measurements are supplied in these recordings.


def simulated_exam(scenario_id: str, exam_id: str, seconds: int, *, deteriorated: bool = False):
    if exam_id not in load_scenario(scenario_id)["exam_ids"]:
        raise ValueError("Examination outside the catalog.")
    return None  # Findings become evidence only when the recorded answer is saved.
