"""Two-state controller. No language interpretation or generic clinical thresholds."""
from contracts import ClinicalEvent, ClinicalState, ProtocolState


def evaluate_hsm(state: ProtocolState, event: ClinicalEvent) -> ProtocolState:
    if event.episode_id != state.episode_id:
        raise ValueError("The event belongs to another episode.")
    if event.t_sim < state.updated_at_sim:
        raise ValueError("State changes must be chronological.")
    data = state.model_dump()
    if event.type == "critical_event":
        data.update(hsm_state=ClinicalState.CRITICAL, interview_enabled=False,
                    check_pending=False, reason="Evento crítico estructurado. Valoración focalizada A/B/C.")
    elif state.hsm_state == ClinicalState.CRITICAL:
        # No automatic downgrade, including after YES/YES or handoff.
        return state
    elif event.type in ("recheck_requested", "reassessment_event", "human_review_requested"):
        data.update(interview_enabled=False, check_pending=True,
                    reason="Revisión solicitada: repetir conciencia y respiración.")
    elif event.type == "initial_check":
        values = [event.payload.get("consciousness"), event.payload.get("breathing")]
        if any(v not in ("YES", "NO", "UNKNOWN") for v in values):
            raise ValueError("The check accepts YES, NO or UNKNOWN only.")
        if "NO" in values:
            data.update(hsm_state=ClinicalState.CRITICAL, interview_enabled=False,
                        check_pending=False, reason="Compromiso actual registrado por el operador en el chequeo.")
        elif "UNKNOWN" in values:
            data.update(interview_enabled=False, check_pending=True,
                        reason="Información esencial desconocida; solicitar comprobación al compañero.")
        else:
            data.update(interview_enabled=True, check_pending=False,
                        reason="Conciencia y respiración comprobadas. Entrevista habilitada; no implica ausencia de riesgo.")
    else:
        return state
    data.update(state_version=state.state_version + 1, updated_at_sim=event.t_sim,
                trigger_event_id=event.event_id)
    return ProtocolState.model_validate(data)


def require_action(state: ProtocolState, action: str) -> None:
    if action == "interview" and not state.interview_enabled:
        raise ValueError("La entrevista está bloqueada por el estado o el chequeo pendiente.")
    if action not in {"interview", "examine", "handoff", "recheck"}:
        raise ValueError("Acción no autorizada.")
