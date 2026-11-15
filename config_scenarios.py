"""Private simulation fixtures. Only public_profile/catalog are inference context.

Values and provenance follow the supplied 2026-11-14 engineering specification.
Clinical pending items are deliberately not auto-filled.
"""
from copy import deepcopy

EXAMS = {
    "blood_pressure": {"label": "Presión arterial", "unit": "mmHg"},
    "temperature": {"label": "Temperatura", "unit": "°C"},
    "respiratory_rate": {"label": "Frecuencia respiratoria", "unit": "/min"},
    "pulse": {"label": "Frecuencia cardíaca", "unit": "bpm"},
    "spo2": {"label": "SpO₂", "unit": "%"},
    "abdomen": {"label": "Palpación abdominal", "unit": "descripción"},
    "skin": {"label": "Piel / conjuntivas", "unit": "descripción"},
    "capillary_refill": {"label": "Relleno capilar", "unit": "s"},
    "airway": {"label": "A · Habla y signos de vía aérea", "unit": "descripción"},
    "breathing_work": {"label": "B · Trabajo respiratorio", "unit": "descripción"},
    "circulation": {"label": "C · Signos circulatorios", "unit": "descripción"},
}

SCENARIOS = {
    "N02": {
        "title": "Mareos y hallazgo digestivo", "delay_seconds": 900,
        "public_profile": {"patient_id": "CM-4", "age": 38, "sex": "Mujer", "role": "Especialista de misión",
            "mission_day": 210, "history": ["Sobreuso de rodilla derecha, día 198"],
            "allergies": "Sin alergias farmacológicas conocidas registradas", "regular_medications": "No documentadas",
            "historical_baselines": {"pulse": 64, "blood_pressure": "116/74", "spo2": 98, "temperature": 36.5}, "provenance": "[B]"},
        "opening": "I've felt very lightheaded and weak since yesterday.",
        "exam_ids": ["blood_pressure", "temperature", "respiratory_rate", "pulse", "spo2", "abdomen", "skin", "capillary_refill"],
        "private_exams": {"blood_pressure": ("108/70", "[G]"), "temperature": (36.5, "[A]"),
            "respiratory_rate": (18, "[A]"), "abdomen": ("Abdomen blando; sensibilidad epigástrica leve", "[A]"),
            "skin": ("Palidez conjuntival", "[A]"), "capillary_refill": ("~3", "[A]")},
        "hidden_truth": "Posible sangrado digestivo alto asociado a ibuprofeno; hipótesis oculta, no diagnóstico confirmado.",
        "actor_notes": "Solo cuando se pregunte: deposiciones oscuras desde ayer, casi negras, pegajosas y con olor intenso; dos episodios; sin sangre roja visible ni hematemesis; ibuprofeno un par de veces esta semana. No hay otras respuestas textuales completas en los adjuntos.",
        "pending": ["Chequeos iniciales a cargo del operador, sin valores por defecto.", "Inconsistencia del guion sobre ponerse de pie en microgravedad: no ofrecer PA ortostática."],
        "schedule": [],
    },
    "N04": {
        "title": "Erupción y deterioro respiratorio", "delay_seconds": 1320,
        "public_profile": {"patient_id": "CM-5", "age": 35, "sex": "Mujer", "role": "Especialista de misión",
            "mission_day": 60, "history": [], "allergies": "Sin alergias farmacológicas ni alimentarias conocidas registradas",
            "regular_medications": "No documentadas", "historical_baselines": {"pulse": 70, "blood_pressure": "110/70", "spo2": 99, "temperature": 36.7}, "provenance": "[B]"},
        "opening": "I've developed an itchy rash on my arms and chest. It started about ten minutes ago.",
        "exam_ids": ["blood_pressure", "respiratory_rate", "skin", "capillary_refill", "pulse", "spo2", "temperature", "airway", "breathing_work", "circulation"],
        "private_exams": {"blood_pressure": ("118/74", "[B]"), "respiratory_rate": (18, "[B]"),
            "temperature": (36.8, "[B]"), "skin": ("Erupción urticariforme", "[B]"), "capillary_refill": ("<2", "[B]")},
        "private_late_exams": {"blood_pressure": ("90/58", "[G]"), "respiratory_rate": (26, "[B]"),
            "skin": ("Erupción urticariforme más extensa", "[B]/[D]"), "capillary_refill": ("3–4", "[B]")},
        "hidden_truth": "Reacción progresiva posiblemente relacionada con alimento nuevo; no diagnóstico confirmado [D].",
        "actor_notes": "El relato de dificultad respiratoria se introduce únicamente al producirse el evento T+2. Las respuestas adicionales las ingresa el operador.",
        "pending": ["Chequeos iniciales manuales.", "Campos A/B/C ilustrativos pendientes de revisión clínica; no incluyen tratamientos."],
        "schedule": [{"id": "deterioration", "at": 120, "type": "critical_event",
            "payload": {"crew_statement": "My voice is getting hoarse, and I'm starting to have trouble breathing. It feels like my throat is tightening."}}],
    },
    "N06": {
        "title": "Fiebre y pérdida de enlace", "delay_seconds": 900,
        "public_profile": {"patient_id": "CM-6", "age": 40, "sex": "Varón", "role": "Ingeniero de vuelo",
            "mission_day": 250, "history": [], "allergies": "Sin alergias farmacológicas conocidas registradas",
            "regular_medications": "Sin medicación habitual registrada", "historical_baselines": {"pulse": 66, "blood_pressure": "120/78", "spo2": 98, "temperature": 36.6}, "provenance": "[B]"},
        "opening": "I've been feeling feverish and unusually tired since yesterday. I think I'm getting worse.",
        "exam_ids": ["blood_pressure", "temperature", "respiratory_rate", "pulse", "spo2"],
        "private_exams": {"blood_pressure": ("124/78", "[B]"), "respiratory_rate": (18, "[B]")},
        "private_late_exams": {"blood_pressure": ("104/68", "[G]"), "respiratory_rate": (20, "[B]")},
        "hidden_truth": "Sin diagnóstico definido; no asignar etiología infecciosa específica.",
        "actor_notes": "Si se pregunta por temperatura inicial: 38,4 °C referida aproximadamente 10 minutos antes; registrar como crew_reported, no como sensor. A T+6 h el evento incorpora la declaración de 39,1 °C. La confirmación por termómetro requiere una nueva entrada manual.",
        "pending": ["Retraso 15 min y recuperación T+7 h propuestos [D].", "Chequeos iniciales manuales.", "El valor de temperatura referido no equivale a un examen medido."],
        "schedule": [
            {"id": "link_down", "at": 1200, "type": "link_change", "payload": {"status": "DOWN"}},
            {"id": "reassessment", "at": 21600, "type": "reassessment_event", "payload": {"crew_statement": "Me siento más débil; refiero una temperatura de 39,1 °C."}},
            {"id": "link_up", "at": 25200, "type": "link_change", "payload": {"status": "UP"}},
        ],
    },
}


def load_scenario(scenario_id: str) -> dict:
    if scenario_id not in SCENARIOS:
        raise ValueError("Escenario desconocido.")
    return deepcopy(SCENARIOS[scenario_id])


def exam_catalog(scenario_id: str) -> dict:
    return {key: deepcopy(EXAMS[key]) for key in SCENARIOS[scenario_id]["exam_ids"]}


def telemetry_at(scenario_id: str, seconds: int, *, deteriorated: bool = False) -> dict:
    if scenario_id == "N02":
        return {"pulse": round(100 + 8 * min(1, max(0, (seconds + 3600) / 3600)), 1), "spo2": 98}
    if scenario_id == "N04":
        if deteriorated:
            return {"pulse": 124, "spo2": 92}
        return {"pulse": round(72 + 20 * min(1, max(0, (seconds + 900) / 900)), 1), "spo2": 98}
    if scenario_id == "N06":
        fraction = min(1, max(0, seconds / 21600))
        return {"pulse": round(98 + 14 * fraction, 1), "spo2": round(98 - fraction, 1)}
    raise ValueError("Escenario desconocido.")


def simulated_exam(scenario_id: str, exam_id: str, seconds: int, *, deteriorated: bool = False):
    """Called only after an exam request. None means no scripted measured result."""
    scenario = load_scenario(scenario_id)
    if exam_id not in scenario["exam_ids"]:
        raise ValueError("Exploración fuera del catálogo.")
    if exam_id in ("pulse", "spo2"):
        return telemetry_at(scenario_id, seconds, deteriorated=deteriorated)[exam_id], "[G]/[D]"
    late = deteriorated if scenario_id == "N04" else seconds >= 21600
    if late:
        return scenario.get("private_late_exams", {}).get(exam_id)
    return scenario["private_exams"].get(exam_id)
