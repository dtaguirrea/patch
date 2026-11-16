# PATCH · Care beyond Earth

PATCH simulates medical assessment and delayed communication during a mission to Mars. It uses fictional cases, Streamlit, SQLite and deterministic control logic. **It is a demonstration, not a clinically validated medical device or a mission-approved emergency protocol.**

The entire interface, built-in prompts, case descriptions, new report text and documentation are in English. Previously saved transcripts and packet snapshots retain their original wording; start a **new episode** to demonstrate the English version from the beginning.

## Run on Windows (PowerShell)

Requires Python 3.11 or later. Extract the archive and copy the contents of `patch-dev` into your project, including **all four files in `case_data/` and `emergency_guidance.py`**.

```powershell
Set-Location "C:\Users\maind\OneDrive\Escritorio\patch\patch"
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

If `.venv` already exists, skip its creation. Open http://localhost:8501. You do not need to activate the virtual environment. `./start.ps1` is an alternative launcher; if PowerShell blocks scripts, use the commands above without changing system execution policies.

## Run on WSL / Linux / macOS

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

Alternatively, run `bash start.sh`. Initial dependency installation needs package-registry access. After installation, the simulation makes no model/API calls and needs no API keys. Stop the server with Ctrl+C. Use `--server.port 8502` if port 8501 is occupied.

## Mandatory safety check

Before any interview turn, the operator must explicitly answer and save **both** questions:

1. **Is the person responsive (responds to your voice or a gentle shoulder tap)?**
2. **Is the person breathing normally (not just gasping)?**

Neither question has a default answer. “No” to question 1 means **no response**, not simply confusion or sleepiness. Choose Unknown if you cannot establish the finding.

| Responses | Application behavior |
|---|---|
| Either unselected | Confirmation disabled; no interview |
| YES / YES | Save both answers, then enable the interview |
| UNKNOWN with no NO | Save the uncertainty, request a check, keep the interview blocked |
| NO / YES | Critical pathway: unresponsive but breathing normally |
| YES / NO | Critical pathway: responsive with breathing difficulty |
| NO / NO | Critical pathway: unresponsive and not breathing normally |
| NO / UNKNOWN or UNKNOWN / NO | Critical pathway with an urgent reassessment prompt; no invented finding |

Selecting a NO displays guidance immediately, even before confirmation. Only confirmation persists the answers and performs a state transition. Both recorded replay and the generic mock are gated by the backend as well as the interface.

Emergency guidance is deterministic and independent of MedGemma. It distinguishes the three situations above, prioritizes local help, and explains the applicable emergency pathway. It is based on published terrestrial adult first-aid guidance. Spacecraft positioning and resuscitation techniques require mission-approved procedures and clinical review; no microgravity technique is invented here. See [docs/SAFETY_GUIDANCE.md](docs/SAFETY_GUIDANCE.md).

In the critical screen, **Recheck responsiveness and breathing** updates the guidance and sends another critical snapshot. It does not automatically downgrade CRITICAL or restart the interview.

## Demo workflow

The default screen is designed for a short product walkthrough: case selection, one active clinical step and a compact mission-link panel. The sidebar clearly labels recorded/mock interviews and no live AI. Developer records, saved-case identifiers and raw JSON are hidden behind **Technical details**.

1. Choose **Case 2 · Left flank pain** (the shorter recorded case) or **Case 1 · Abdominal pain**, then click **Start case →**. A new case preserves all previous episodes.
2. Explicitly select both safety answers and click **Confirm safety check**. Both must be Yes to enter the interview. **Unable to check** is stored as UNKNOWN and keeps the interview blocked.
3. Follow **Safety → Interview → Vitals → Exam → Handoff**. The active step is highlighted. Read the recorded question and demo answer; click **Use demo answer →** to save that answer and advance. Merely displaying the answer does not record it or send it to Earth.
4. Review the readable SBAR handoff, then click **Send handoff to Earth →**. An emergency can send a critical update before this normal flow completes.
5. Use the single **Advance time (+...)** button. By default it reaches the next pending message arrival or scheduled simulation event, falling back to one minute when neither exists. The amount is shown before the click. No timer runs in the background, and advancing time never answers questions.
6. Watch **Mission link** change from **In transit** to **Received on Earth**. **Earth inbox** contains only delivered snapshots, never current onboard information that has not arrived.
7. For advanced operation, enable **Technical details**: resume a saved case, choose a fixed time step, inspect/export raw records or close a completed case. These controls are unnecessary for the video.

All four cases use a 15-minute one-way simulation delay. No timed clinical deterioration or link outage is fabricated for these recordings. In Case 4, the change in symptoms is recorded only when its demo answer is saved; advancing time alone cannot trigger it.

No free-text reply editing is offered: subsequent recorded questions may depend on the original answers. The catalog contains only the four supplied recordings. Previous scenario fixtures and their special simulation behavior have been removed.

See [docs/DEMO_VIDEO.md](docs/DEMO_VIDEO.md) for a short recording sequence.

## Included cases — this release contains exactly four

| Case | Recorded sequence | Reported observations |
|---|---|---|
| C01 · Abdominal pain | 8 history turns, 1 vital-sign turn, 1 examination turn | HR 96 bpm; SpO₂ 98%; localized lower-right abdominal tenderness |
| C02 · Left flank pain | 6 history turns, 1 vital-sign turn, 1 examination turn | HR 108 bpm; SpO₂ 98%; limited crewmate examination |
| C03 · Lightheadedness and weakness | 9 history turns, 2 vital-sign turns, 1 examination turn | HR 108 bpm; SpO₂ 98%; BP 108/70 mmHg; respiratory rate 12/min; reported abdominal findings |
| C04 · Palpitations and a change in condition | 4 history turns, 1 vital-sign turn, then a reported clinical change | HR 96 bpm; SpO₂ 98%; no completed cardiac examination |

The new attachment supplies all four JSON recordings. Answers are retained verbatim, including source spelling; machine phase markers are removed from crew-facing questions. Each normalized case retains the original filename, SHA-256 hash, context and source dialogue indices. The model used for the recordings was `google/medgemma-27b-text-it`; it is not run by this app.

**Case 4 stops for a second mandatory safety check.** Its final reply reports a new near-fainting episode. The source ends with an unanswered `RECHECK_SUGGESTED`, so the controller pauses the interview and requests both current safety answers. Yes/Yes permits a partial handoff of the available findings. No selects the emergency pathway; unknown keeps the check pending. PATCH does not fabricate a recovery, completed examination, further dialogue or diagnosis. The model text itself never selects CRITICAL.

The generated report for Case 3 is truncated/unparseable. PATCH does not import any source model report as clinical evidence; it builds a readable deterministic handoff from the recorded dialogue and observations for every case.

These recordings provide no demographic records, continuous sensor feed or observation timestamps. Values are saved as `crew_reported` with unknown observation time only after their answer is confirmed. Missing measurements remain unknown. Focused-exam requests in the source exceed its vital-only catalog; they are replayed as historical dialogue, not approved clinical procedures. Case 3's references to standing are likewise preserved as reported language, not a validated microgravity maneuver.

Saved episodes belonging to removed scenarios are filtered out of the UI, including Technical details. They are not physically deleted from an existing SQLite file. A previous active selection outside the new catalog cannot be resumed or cause a catalog lookup crash.

## Persistence and updates

SQLite is created at `data/patch_mvp.sqlite3`. Episodes, checks, workflow position, transcripts, observations and messages survive a restart. Start a new case to restart the workflow while preserving previous episodes. Override the database path with `PATCH_DB_PATH` if needed.

Existing evidence and immutable packets are not translated or rewritten during an update. Older safety checks asked about “responding appropriately”; they are not interpreted as proof of unresponsiveness. The emergency display asks for a new explicit check when it cannot establish the current finding.

The archive excludes generated databases, virtual environments, credentials and caches. This is a local application without authentication; it is not configured for public hosting or real patient records.

## Modules

| File | Responsibility |
|---|---|
| `app.py` | English guided interface, safety questions, emergency display and one clock control |
| `controller.py` | Transactional commands, safety clearance, workflow, handoff and scheduling |
| `core_hsm.py` | ASSESSMENT / CRITICAL state transitions |
| `emergency_guidance.py` | Deterministic response-specific instructions and source links |
| `contracts.py` | Pydantic data contracts |
| `config_scenarios.py` | Public profiles and private simulation fixtures |
| `case_data/` | C01–C04 recorded cases with source filenames, hashes and terminal markers |
| `llm_anamnesis.py` | Recorded-question replay and generic mock |
| `space_link_db.py` | SQLite persistence and delayed one-way transport |

A future live backend must retain the safety gate, provenance checks and stale-response rejection. Network inference must run outside database write transactions with timeouts/fallback. This release does not claim live MedGemma access or physical cancellation of inference.

## Git workflow

Keep **working branch → dev → main**. After copying the complete update, review `git status` and `git diff`, commit the intended files and push your working branch. Include both new code and case data:

```bash
git add app.py contracts.py controller.py core_hsm.py emergency_guidance.py config_scenarios.py space_link_db.py llm_anamnesis.py requirements.txt README.md docs case_data .streamlit start.ps1 start.sh .gitignore
git commit -m "Add English safety-gated assessment and emergency guidance"
git push -u origin HEAD
```

No tests were added or test suites run, as requested. The documented review covers syntax, startup and manual command walkthroughs; it is not clinical validation. See [docs/RESULTS.md](docs/RESULTS.md).
