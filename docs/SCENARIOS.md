# Demonstration walkthroughs

Start a new episode for the English UI update. All patient data are fictional. Initial responsiveness and breathing answers are not supplied by the cases: the operator must make explicit simulation selections.

## C01 · Abdominal pain

Choose Case 1 and start it. Answer and save both safety questions. YES/YES enables eight history turns, one vital-sign turn (96 bpm / 98%) and one reported abdominal examination turn. Each click records only the current scripted response; future answers remain private. Then generate the handoff and advance fifteen minutes to deliver messages sent at T0.

The recorded dialogue explores location/migration, onset, character, severity, associated symptoms, appetite and dietary changes. It does not establish a confirmed diagnosis. Missing blood pressure, respiratory rate and temperature remain unknown.

## C02 · Severe left flank pain

After the mandatory safety check, replay six history turns, one vital-sign turn (108 bpm / 98%) and the crewmate's report of a limited examination. Generate the handoff, then advance the clock to deliver it. Observation times are unknown in the supplied JSON; PATCH records the entry time separately.

## Negative safety responses

Start a separate fictional episode for each branch. Select the two answers and observe the immediate guidance preview. Confirm both answers to persist the check.

- NO responsiveness / YES normal breathing opens the unresponsive-with-normal-breathing pathway.
- YES responsiveness / NO normal breathing opens the responsive-with-breathing-difficulty pathway.
- NO / NO opens the suspected-cardiac-arrest pathway.
- UNKNOWN keeps findings unresolved and the interview blocked. Any accompanying NO also activates CRITICAL.

No interview question should appear before affirmative safety clearance. The emergency screen offers another explicit check without restarting the interview. Critical updates contain the recorded answers and guidance snapshot. Guidance is a fictional adult demo adaptation of terrestrial sources, not a spaceflight protocol.

## N02 · Original lightheadedness scenario

Complete safety, answer five generic questions and document the requested vital readings or their unavailability. Continue through configured examinations and generate the handoff. Only report the gastrointestinal history when asked: dark stools since yesterday, almost black, sticky and strong-smelling, two episodes. When asked about medicines, report ibuprofen a couple of times that week. Do not convert these reports into a confirmed diagnosis.

## N04 · Structured respiratory deterioration

From T0, enter 2 in Minutes to advance and click Advance time. The structured event triggers even if the initial check is unfinished. It records pulse 124 / SpO2 92 and the reported deterioration, blocks interview and sends a critical update.

Older YES/YES answers are not treated as current after deterioration. Use the emergency recheck to establish current responsiveness/breathing and select the appropriate guidance. Record subsequent findings only after the immediate emergency actions in the fictional demonstration. Blood pressure 90/58 is added only if requested and recorded.

From T+2, advance 20 minutes for the original alert at T+22; advance another 2 for the original critical event at T+24. Additional updates have their own creation/delivery times.

## N06 · Outage and reassessment

Complete the first guided assessment. From T0, advance 25 minutes: the initial alert arrives at T+15 and the link goes DOWN at T+20. Generate the first handoff, which remains QUEUED.

From T+25, advance 335 minutes to T+6 hours. The simulator records temperature 39.1 as crew_reported and requests new safety checks. Complete them, answer two focused reassessment questions and document the new readings. Advance 10 minutes and generate the next handoff. Advance 50 minutes to recover the link at T+7 hours, then 15 to deliver queued messages.

The clock input is an increment, not an absolute destination. Advancing time never answers questions or automatically completes handoff. Requesting human review interrupts the workflow and requires a new safety check while preserving history.

## Closure and history

A documented closure is available after a handoff. The episode retains its HSM state and records a final update; closure does not certify clinical recovery. It stops new episode events and samples. Previously saved evidence and immutable packet snapshots remain unchanged, including any Spanish records created before the English update.
