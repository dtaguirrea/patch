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
                    check_pending=False, reason="Structured critical event. Emergency assessment is required.")
    elif state.hsm_state == ClinicalState.CRITICAL:
        # No automatic downgrade, including after YES/YES or handoff.
        return state
    elif event.type in ("recheck_requested", "reassessment_event", "human_review_requested"):
        data.update(interview_enabled=False, check_pending=True,
                    reason="Review requested: repeat responsiveness and breathing checks.")
    elif event.type == "initial_check":
        values = [event.payload.get("consciousness"), event.payload.get("breathing")]
        if any(v not in ("YES", "NO", "UNKNOWN") for v in values):
            raise ValueError("The check accepts YES, NO or UNKNOWN only.")
        if "NO" in values:
            data.update(hsm_state=ClinicalState.CRITICAL, interview_enabled=False,
                        check_pending=False, reason="An immediate safety concern was recorded by the operator.")
        elif "UNKNOWN" in values:
            data.update(interview_enabled=False, check_pending=True,
                        reason="Essential safety information is unknown; ask a crewmate to check.")
        else:
            data.update(interview_enabled=True, check_pending=False,
                        reason="Responsiveness and normal breathing checked. Interview enabled; this does not rule out serious illness.")
    else:
        return state
    data.update(state_version=state.state_version + 1, updated_at_sim=event.t_sim,
                trigger_event_id=event.event_id)
    return ProtocolState.model_validate(data)


def require_action(state: ProtocolState, action: str) -> None:
    if action == "interview" and not state.interview_enabled:
        raise ValueError("The interview is blocked by the current state or pending safety check.")
    if action not in {"interview", "examine", "handoff", "recheck"}:
        raise ValueError("Action not authorized.")
