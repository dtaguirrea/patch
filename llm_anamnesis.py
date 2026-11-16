"""Explicit deterministic mock: no network calls, credentials or clinical inference.

The replacement boundary is InterviewBackend.generate(context). It receives only
persisted visible context, never the private scenario. The controller owns all
writes and checks the state revision before accepting the returned turn.
"""
from uuid import uuid4
from contracts import ClinicalAssessmentTurn

# Questions are generic and do not encode answers or hidden diagnoses.
QUESTIONS = [
    "When did your symptoms start, and how have they changed since then?",
    "How would you describe the main concern, and which activities does it affect?",
    "Have you noticed any other changes, such as in your skin, breathing, digestion or stools?",
    "Have you recently taken any medicines or supplements, or tried a new food?",
    "Can you describe those changes in more detail and say when they occurred?",
    "If relevant, ask the crewmate for an examination from the catalog and record the result.",
    "Is there anything else you would like to report, or any change since this assessment began?",
]

RECHECK_QUESTIONS = [
    "What has changed or worsened since the previous assessment?",
    "Are there any new symptoms or other information relevant to this reassessment?",
]


class InterviewBackend:
    name = "Deterministic mock · no MedGemma connection"

    def generate(self, context: dict) -> ClinicalAssessmentTurn:
        instruction = context.get("instruction")
        if instruction is not None:
            return ClinicalAssessmentTurn(turn_id=uuid4().hex, episode_id=context["episode_id"],
                state_version=context["state_version"], text=instruction["text"],
                backend="recorded" if instruction["recorded"] else "mock",
                question_index=instruction["index"],
                action_reason="Recorded question replay; no live inference." if instruction["recorded"] else "Generic mock question.")
        answered = sum(1 for item in context["dialogue"] if item["type"] == "patient_message")
        index = min(answered, len(QUESTIONS) - 1)
        text = QUESTIONS[index]
        return ClinicalAssessmentTurn(
            turn_id=uuid4().hex, episode_id=context["episode_id"], state_version=context["state_version"],
            text=text, next_action="examine" if index == 5 else "ask", question_index=index,
            open_uncertainties=["Human clinical review is pending. The mock does not interpret free text."],
        )
