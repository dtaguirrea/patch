# Four recorded cases

The only active case identifiers are C01, C02, C03 and C04. Every case starts with unanswered responsiveness and normal-breathing checks. These initial answers must be explicitly supplied by the demo operator; dialogue about breathing never substitutes for them.

## Case 1 · Abdominal pain

Ten recorded answers: eight history, one vital-sign and one examination turn. The record describes pain beginning near the belly button and moving toward the lower right abdomen. The vital reply supplies HR 96 bpm and SpO₂ 98%. The final answer reports localized tenderness. Blood pressure, respiratory rate and temperature remain unknown.

## Case 2 · Left flank pain

Eight recorded answers: six history, one vital-sign and one examination turn. The record describes sudden left flank pain, intermittent waves and urine that looked pink. The vital reply supplies HR 108 bpm and SpO₂ 98%. The reported examination is limited. A symptom merely mentioned in an interviewer question is not treated as a finding.

## Case 3 · Lightheadedness and weakness

Twelve recorded answers: nine history, two vital-sign and one examination turn. The dialogue records progressive lightheadedness/weakness, reported dark sticky stools and reported ibuprofen use. HR 108 bpm and SpO₂ 98% appear in the first vital reply; BP 108/70 mmHg and respiratory rate 12/min appear in the next. The last answer reports a soft abdomen and mild upper-midline tenderness. Temperature remains unknown.

The source report failed JSON parsing and is truncated. The application uses the transcript and supplied observations, not that report. Original spelling and references to getting up/standing are preserved as recorded language; they do not establish a validated microgravity examination procedure.

## Case 4 · Palpitations and a change in condition

Six recorded answers: four history replies, one vital reply (HR 96 bpm, SpO₂ 98%), then a reply describing a change in condition. The last reply follows a question about examination availability but supplies no examination result. It reports feeling near fainting, gray vision and shakiness. The source then requests a safety recheck and ends without a response.

Saving that last answer emits a structured recheck request and pauses the interview. The fixed responsiveness and breathing questions reappear. Both Yes answers permit a partial handoff; either No activates CRITICAL; Unknown keeps the recheck pending. No completed cardiac examination, recovery, later dialogue, diagnosis or automatic downgrade is invented. Initial Yes/Yes is not reused for this second check.

## Time and communication

All four cases use a proposed 15-minute one-way delay for the demonstration. There are no continuous sensors or scheduled clinical changes in these fixtures. Recording answers does not advance the clock. The one Advance time button reaches the next pending delivery, or advances one minute when no delivery is pending. Its optional fixed interval is available in Technical details. The backend still supports chronological event handling.

Case 4 changes through its recorded answer, not through a timed event. If its update was sent after a clock advance, it has its own later arrival time. Earth only sees delivered snapshots.

## Provenance and retired cases

`case_data/C01.json` through `C04.json` retain source hashes, filenames and dialogue indices. All extracted observations are crew-reported and have unknown observation times. The raw notebook model reports are not used as evidence. No notebook is executed or required for the demo.

The previous scenario fixtures are removed from the catalog. Existing SQLite histories for retired identifiers are left intact but never listed or resumed by the UI.
