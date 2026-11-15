"""Deterministic adult safety guidance, independent of the interview backend.

Terrestrial recognition/first-aid principles are adapted only at the level of
mission escalation. This module does not prescribe a microgravity CPR technique.
See docs/SAFETY_GUIDANCE.md for sources and clinical-review boundaries.
"""
QUESTION_SET = "responsiveness_normal_breathing_v2"
SOURCES = [
    {"title": "AHA 2025 Adult Basic Life Support", "url": "https://cpr.heart.org/en/resuscitation-science/cpr-and-ecc-guidelines/adult-basic-life-support"},
    {"title": "AHA / American Red Cross 2024 First Aid Guidelines", "url": "https://cpr.heart.org/en/resuscitation-science/2024-first-aid-guidelines"},
    {"title": "American Red Cross: Unresponsive and Breathing", "url": "https://www.redcross.org/take-a-class/resources/learn-first-aid/unresponsive-and-breathing-person"},
]
SCOPE = ("Adult simulation guidance based on terrestrial first-aid sources. "
         "Spacecraft positioning, restraints and resuscitation techniques must follow "
         "mission-approved procedures reviewed by the clinical team.")
ESCALATE = "Activate the mission emergency response and call a trained crewmate now. Do not wait for an Earth reply."


def guidance_for_answers(consciousness=None, breathing=None, *, critical=False):
    """NO responsiveness means no response, not merely confusion or sleepiness."""
    responsive = consciousness if consciousness in ("YES", "NO", "UNKNOWN") else "UNKNOWN"
    normal = breathing if breathing in ("YES", "NO", "UNKNOWN") else "UNKNOWN"
    if responsive == "NO" and normal == "NO":
        branch, title = "unresponsive_abnormal_breathing", "Unresponsive and not breathing normally"
        steps = [ESCALATE,
            "Treat this as suspected cardiac arrest: start CPR immediately, following the mission-approved resuscitation procedure. Gasping is not normal breathing.",
            "Have another crewmate obtain an AED if available. Use it as soon as possible and follow its prompts.",
            "Continue the emergency response until qualified responders take over or the mission procedure directs otherwise."]
    elif responsive == "NO" and normal == "YES":
        branch, title = "unresponsive_normal_breathing", "Unresponsive but breathing normally"
        steps = [ESCALATE,
            "Maintain a clear airway using your training and the mission airway/positioning procedure. Account for possible injury before moving the person.",
            "Stay with the person and repeatedly check breathing. If normal breathing stops or becomes gasping, switch to the CPR/AED pathway."]
    elif responsive == "YES" and normal == "NO":
        branch, title = "responsive_breathing_difficulty", "Responsive with abnormal or difficult breathing"
        steps = [ESCALATE,
            "Help the person adopt a position that makes breathing easier, as safely permitted by the spacecraft environment.",
            "Monitor responsiveness and breathing. A breathing difficulty answer alone does not establish cardiac arrest.",
            "If the person becomes unresponsive and is not breathing normally, switch immediately to the CPR/AED pathway."]
    elif responsive == "YES" and normal == "YES" and not critical:
        branch, title = "checks_complete", "Both safety checks completed"
        steps = ["The interview may proceed after both answers are saved. These checks do not rule out serious illness."]
    else:
        branch, title = "urgent_reassessment" if critical or "NO" in (responsive, normal) else "check_required", "Check responsiveness and breathing now"
        steps = ([ESCALATE] if critical or "NO" in (responsive, normal) else ["Ask a crewmate to verify both safety checks; do not assume a normal finding."])
        steps += ["Check for a response to your voice and a gentle shoulder tap while observing breathing. Do not spend more than 10 seconds on this initial check.",
            "If the adult is unresponsive and not breathing normally or only gasping, start the CPR/AED pathway immediately."]
    return {"branch": branch, "title": title, "steps": steps, "scope": SCOPE,
            "sources": SOURCES, "answers": {"consciousness": responsive, "breathing": normal},
            "question_set": QUESTION_SET, "version": "2026-11-15-en-1"}
