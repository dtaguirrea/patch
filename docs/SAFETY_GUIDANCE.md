# Safety questions and emergency guidance

## Wording and meaning

The first question is affirmative: **Is the person responsive (responds to your voice or a gentle shoulder tap)?** NO establishes no response; it must not be used to mean merely confused, drowsy or not answering appropriately. The second asks **Is the person breathing normally (not just gasping)?**

Both questions must be explicitly answered and saved before an interview. YES/YES permits the workflow; unknown findings require reassessment. Either NO selects the critical pathway. A partially filled form never starts the interviewer.

## Guidance routing

| Responsiveness | Normal breathing | Branch |
|---|---|---|
| NO | NO | Suspected cardiac arrest; CPR/AED pathway |
| NO | YES | Unresponsive with normal breathing; airway protection and monitoring |
| YES | NO | Responsive with breathing difficulty; urgent help, positioning for comfort, monitoring |
| UNKNOWN / unselected | Any | Establish the missing finding; escalate immediately when a NO or critical event is present |
| YES | UNKNOWN / unselected | Establish breathing; keep interview blocked |
| YES | YES | Interview allowed after saving, unless the episode remains CRITICAL |

A breathing difficulty answer alone never produces an unconditional CPR instruction. The critical screen stays available after the interview stops. Selecting NO shows an immediate preview; the preview is not a saved clinical observation. Saving both answers records the check and, when applicable, creates the critical update.

A new emergency recheck may change the displayed instructions while keeping the episode CRITICAL. This deliberate lack of automatic downgrade avoids restarting the interview merely because later answers become YES/YES. A new episode can be used to restart a demonstration.

## Sources and scope

The recognition and escalation principles were checked against:

- [American Heart Association: 2025 Adult Basic Life Support](https://cpr.heart.org/en/resuscitation-science/cpr-and-ecc-guidelines/adult-basic-life-support).
- [American Heart Association / American Red Cross: 2024 First Aid Guidelines](https://cpr.heart.org/en/resuscitation-science/2024-first-aid-guidelines).
- [American Red Cross: Unresponsive and Breathing](https://www.redcross.org/take-a-class/resources/learn-first-aid/unresponsive-and-breathing-person).

Accessed 2026-11-15. The source links are displayed beside the instructions and included in the guidance snapshot. The wording in PATCH is a short paraphrase, not a complete reproduction of the guidelines.

These sources describe terrestrial adult first aid. PATCH's local mission response and instruction not to wait for a delayed Earth reply are application design adaptations. No NASA approval, validated spaceflight protocol, drug regimen, microgravity CPR technique or automatic execution of treatment is claimed. Spacecraft-specific positioning, restraints and resuscitation procedures require mission approval and review by the team's clinician before any use outside a fictional demonstration.

## Evidence and audit

Every new check carries `question_set=responsiveness_normal_breathing_v2`. Older records asking whether the person is awake and responding appropriately are insufficient to infer unresponsiveness and route to reassessment instead.

A structured deterioration or recheck request after a saved check invalidates its use as current guidance. `get_safety_guidance` records the supporting event ID/time when there is an applicable check. Each message freezes the guidance version, branch, answers and source URLs at creation. No LLM selects the branch or changes the safety state.
