"""Explicit deterministic mock: no network calls, credentials or clinical inference.

The replacement boundary is InterviewBackend.generate(context). It receives only
persisted visible context, never the private scenario. The controller owns all
writes and checks the state revision before accepting the returned turn.
"""
from uuid import uuid4
from contracts import ClinicalAssessmentTurn

# Questions are generic and do not encode answers or hidden diagnoses.
QUESTIONS = [
    "¿Cuándo comenzó lo que siente y cómo ha cambiado desde entonces?",
    "¿Cómo describiría la molestia principal y qué actividades le dificulta?",
    "¿Ha notado otros cambios, por ejemplo en la piel, respiración, digestión o deposiciones?",
    "¿Ha tomado medicamentos o suplementos, o consumido algún alimento nuevo recientemente?",
    "¿Puede describir con más detalle los cambios que mencionó y cuándo ocurrieron?",
    "Si corresponde al caso, solicite al compañero una exploración del catálogo y registre el resultado.",
    "¿Hay algo más que quiera comunicar o algún cambio desde que comenzó esta evaluación?",
]


class InterviewBackend:
    name = "Mock determinista · sin conexión a MedGemma"

    def generate(self, context: dict) -> ClinicalAssessmentTurn:
        answered = sum(1 for item in context["dialogue"] if item["type"] == "patient_message")
        rechecked = [e for e in context["checks"] if e["t_sim"] >= 21600]
        if rechecked and context["mission"]["scenario_id"] == "N06" and not any(
            e["type"] == "patient_message" and e["t_sim"] >= rechecked[-1]["t_sim"] for e in context["dialogue"]
        ):
            text = "Comparando con la evaluación anterior, ¿qué cambió y qué mediciones nuevas puede comunicar?"
            index = -1
        else:
            index = min(answered, len(QUESTIONS) - 1)
            text = QUESTIONS[index]
        return ClinicalAssessmentTurn(
            turn_id=uuid4().hex, episode_id=context["episode_id"], state_version=context["state_version"],
            text=text, next_action="examine" if index == 5 else "ask", question_index=index,
            open_uncertainties=["Valoración clínica humana pendiente. El mock no interpreta el texto libre."],
        )
