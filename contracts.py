"""Validated, serializable contracts for the PATCH simulation MVP."""
from enum import StrEnum
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class ClinicalState(StrEnum):
    ASSESSMENT = "ASSESSMENT"
    CRITICAL = "CRITICAL"


class LinkStatus(StrEnum):
    UP = "UP"
    DOWN = "DOWN"


class MessageStatus(StrEnum):
    QUEUED = "QUEUED"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"


class MissionClock(Contract):
    mission_id: str
    scenario_id: str
    met_seconds: int = Field(default=0, ge=0)
    one_way_delay_seconds: int = Field(ge=0)
    version: int = Field(default=0, ge=0)
    link_status: LinkStatus = LinkStatus.UP


class TelemetrySample(Contract):
    sample_id: str
    episode_id: str
    patient_id: str
    metric: Literal["pulse", "spo2"]
    value: float | None
    unit: str
    observed_at_sim: int  # Negative times are the pre-activation black box.
    source: Literal["simulated_sensor"] = "simulated_sensor"
    quality: Literal["valid", "missing", "suspect"] = "valid"

    @model_validator(mode="after")
    def missing_signal(self):
        if (self.value is None) != (self.quality == "missing"):
            raise ValueError("A missing signal must have a null value and missing quality.")
        return self


class ClinicalEvent(Contract):
    event_id: str
    episode_id: str
    type: str
    source: str
    t_sim: int = Field(ge=0)
    payload: dict[str, Any] = Field(default_factory=dict)


class ProtocolState(Contract):
    episode_id: str
    hsm_state: ClinicalState = ClinicalState.ASSESSMENT
    state_version: int = Field(default=0, ge=0)
    updated_at_sim: int = Field(default=0, ge=0)
    trigger_event_id: str | None = None
    interview_enabled: bool = False
    check_pending: bool = True
    reason: str = "Pendiente: comprobar conciencia y respiración."


class Observation(Contract):
    observation_id: str
    episode_id: str
    patient_id: str
    metric: str
    value: str | float | None
    unit: str
    observed_at_sim: int | None = None
    entered_at_sim: int = Field(ge=0)
    source: Literal["simulated_sensor", "crew_reported", "exam_entry"]
    quality: Literal["valid", "unknown", "unavailable", "denied", "suspect"] = "valid"
    replaces_observation_id: str | None = None
    provenance: str = "operator_entry"

    @model_validator(mode="after")
    def valid_time(self):
        if self.observed_at_sim is not None and self.observed_at_sim > self.entered_at_sim:
            raise ValueError("An observation cannot come from the future.")
        if self.quality in ("unknown", "unavailable") and self.value is not None:
            raise ValueError("Unknown/unavailable results must have a null value.")
        return self


class ClinicalFinding(Contract):
    """Extension contract; the MVP does not extract clinical entities from chat."""
    finding_id: str
    episode_id: str
    description: str
    category: Literal["symptom", "history", "vital_sign", "physical_exam", "other"]
    status: Literal["present", "denied", "unknown", "not_assessed"]
    source: str
    evidence: str
    source_ref: str
    revision: int = Field(default=0, ge=0)


class ClinicalAssessmentTurn(Contract):
    turn_id: str
    episode_id: str
    state_version: int
    text: str
    backend: Literal["mock"] = "mock"
    next_action: Literal["ask", "examine", "handoff_ready"] = "ask"
    exam_plan: list[str] = Field(default_factory=list)
    action_reason: str = "Guion de demostración determinista; no es inferencia clínica."
    assessment_sufficient: bool = False
    problem_summary: str = ""
    new_findings: list[ClinicalFinding] = Field(default_factory=list)
    working_hypotheses: list[str] = Field(default_factory=list)
    open_uncertainties: list[str] = Field(default_factory=list)
    question_index: int = 0


class MedicalMessage(Contract):
    packet_id: str
    episode_id: str
    kind: Literal["INITIAL_ALERT", "CLINICAL_UPDATE", "CRITICAL_UPDATE"]
    created_at_sim: int
    sent_at_sim: int | None = None
    arrives_at_sim: int | None = None
    delivered_at_sim: int | None = None
    status: MessageStatus = MessageStatus.QUEUED
    state_version: int
    payload: dict[str, Any]


class EpisodeSummary(Contract):
    episode_id: str
    generated_at_sim: int
    generated_by: Literal["deterministic_template"] = "deterministic_template"
    sbar: dict[str, Any]
    observations: list[dict[str, Any]]
    transcript: list[dict[str, Any]]
    checks: list[dict[str, Any]]
    uncertainties: list[str]
    timeline: list[dict[str, Any]]


def format_met(seconds: int | None) -> str:
    if seconds is None:
        return "Sin registrar"
    sign = "+" if seconds >= 0 else "−"
    hours, remainder = divmod(abs(seconds), 3600)
    minutes, sec = divmod(remainder, 60)
    return f"T{sign}{hours:02d}:{minutes:02d}:{sec:02d}"
