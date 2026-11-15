# PATCH · English guided assessment and emergency pathways

PATCH simulates medical assessment and delayed communication during a mission to Mars. It uses fictional cases, Streamlit, SQLite and deterministic control logic. **It is a demonstration, not a clinically validated medical device or a mission-approved emergency protocol.**

The entire interface, built-in prompts, case descriptions, new report text and documentation are in English. Previously saved transcripts and packet snapshots retain their original wording; start a **new episode** to demonstrate the English version from the beginning.

## Run on Windows (PowerShell)

Requires Python 3.11 or later. Extract the archive and copy the contents of `patch-dev` into your project, including **`case_data/` and `emergency_guidance.py`**.

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

## Guided workflow

1. Select a case and click **Start a new case**. The initial alert contains only information known at activation.
2. Complete both safety questions.
3. Follow **History → Vital signs → Examination → Handoff**. Only the current stage is active.
4. For Cases 1 and 2, read the question, optionally preview its recorded answer, and click **Record the case answer and continue**. No live MedGemma inference occurs.
5. At the handoff stage, review the SBAR and click **Generate and send handoff to Earth**. In an emergency, an urgent update is allowed before the normal workflow completes.
6. Use the single **Advance time** button with **Minutes to advance**. Advancing time does not answer questions or complete stages. It processes all intermediate scenario events and packet arrivals.
7. Open **Earth · received packets** to inspect delivered snapshots. Download the trace under **Export and case details**.

No free-text reply editing is offered for recorded cases: subsequent recorded questions may depend on the original answers. The original N02/N04/N06 scenarios still support manual responses to the generic mock.

## Included cases

| Case | Source and behavior |
|---|---|
| C01 · Abdominal pain | Eight recorded history responses, one vital-sign turn (96 bpm / 98%), one reported examination turn |
| C02 · Severe left flank pain | Six history responses, one vital-sign turn (108 bpm / 98%), one reported examination turn |
| N02 | Original lightheadedness / gastrointestinal scenario |
| N04 | Original rash scenario; structured deterioration at T+2 minutes |
| N06 | Original fever scenario; outage at T+20 minutes, recheck at T+6 hours, link recovery at T+7 hours |

The supplied Case 3 folder was empty. No third case was fabricated. C01/C02 preserve the English dialogue from the supplied JSON recordings. Their questions were originally generated with `google/medgemma-27b-text-it`, but the current application replays them locally.

C01/C02 provide no demographics, historical sensor feed or measurement times. Their reported values appear only when the corresponding answer is saved, with `source=crew_reported` and unknown observation time. The 15-minute one-way delay is a demo setting. Blood pressure, temperature and respiratory rate remain unknown when absent. The historical generated reports are not imported as clinical evidence.

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
| `case_data/` | C01/C02 recorded cases with source filenames and hashes |
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
