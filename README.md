# PATCH
## Protocol-Assisted Triage, Communication, and Handoff

PATCH is a prototype for onboard medical assessment during a simulated Mars mission. It helps crew members record immediate safety checks, collect symptoms and available measurements, respond to an urgent change in condition, and prepare a clinical handoff for Earth.

The project demonstrates how structured onboard information gathering can support a crew when communication with a medical team is delayed. Its interface follows a guided sequence, while deterministic rules decide when the interview must pause and emergency guidance must appear.

**Current MVP:** an English-language Streamlit application with four fictional recorded MedGemma interviews, local SQLite storage, and a simulated communication link. No live LLM connection is required.

> Demonstration prototype, not for clinical use. Clinical findings require human review, and onboard emergency procedures require mission-specific validation.

## Features

- Mandatory responsiveness and normal-breathing checks before interviewing.
- Guided collection of history, reported vital signs, and examination findings.
- Separate assessment and critical behavior.
- Predefined emergency guidance based on the crew's safety answers.
- Structured clinical handoffs with recorded evidence and uncertainties.
- Simulated message delivery with a 15-minute one-way delay.
- Persistent episodes, event history, and JSON export.

## Installation

Use Python 3.11 as the reference environment. Run the following commands from the repository root.

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

### Linux, macOS, or WSL

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

If a working `.venv` already exists, skip its creation. Open [http://localhost:8501](http://localhost:8501) and stop the server with **Ctrl+C**.

The main dependencies are **Streamlit**, **Pydantic**, and **pandas**. The demo requires no API key, GPU, or model download.

## How PATCH works

An episode begins when the operator selects a demonstration scenario and clicks **Start case →**. PATCH records the opening complaint and automatically creates an initial alert for the simulated Earth link.

The clinical controller uses two states:

| State | Purpose | What the interface shows |
|---|---|---|
| `ASSESSMENT` | Collect information and prepare a handoff, subject to the safety checks. | Safety questions, interview, findings, and report. |
| `CRITICAL` | Pause interviewing and prioritize the local emergency response. | Emergency guidance, reassessment controls, additional findings, and critical handoff actions. |

The normal operating pathway is called `ASSESSMENT` in the code. It describes the application's workflow; it does not mean that the patient has been declared medically well.

### Mandatory safety checks

Before the interview, PATCH asks:

1. **Is the person responsive?**
2. **Is the person breathing normally (not just gasping)?**

Both answers must be selected and confirmed. Neither is preselected.

| Confirmed answers | Application behavior |
|---|---|
| Both **Yes** | Enables the interview if the episode has not entered `CRITICAL`. |
| **Unknown** on either question, with no **No** | Keeps the check pending and the interview blocked. The screen asks a crewmate to verify the findings. |
| **No** on either question | Enters `CRITICAL`, blocks the interview, displays emergency guidance, and creates a priority alert. |

The uncertainty option is labeled **Unable to check** or **Not sure**, depending on the demonstration view.

Selecting **No** immediately previews guidance. Confirming both answers saves the check and applies the critical transition. A “No” in an ordinary history answer does not trigger this rule.

## Normal operation: ASSESSMENT

Once both safety answers are confirmed as Yes, PATCH permits the guided assessment.

1. **Collect the history.** The interface displays recorded interview questions and astronaut responses about the presenting complaint.
2. **Record available findings.** Supplied measurements and examination descriptions become observations when their corresponding answers are saved.
3. **Review the evidence.** The interface shows the recorded findings and a structured clinical handoff.
4. **Send the handoff.** The operator submits the report to the simulated communication link.
5. **Follow delivery.** The link panel shows its transmission status, and the Earth inbox displays it after arrival.

The visible stages are **Safety → Interview → Vitals → Exam → Handoff**. In the demo, responses advance with **Use demo answer →** or **Next message**. Displaying an answer preview does not save it as patient evidence.

The interview uses recorded MedGemma conversations. It does not generate new answers or diagnoses. Missing measurements remain unavailable, and a reported measurement is not presented as live sensor data.

### If reassessment is needed

A recorded change in condition or **Request urgent review** pauses the interview and requires fresh responsiveness and breathing checks. PATCH also sends an assessment update.

A reassessment request alone does not enter `CRITICAL`. The confirmed safety answers determine what happens next:

- **Yes / Yes:** assessment can continue. If the recording has ended, PATCH opens a partial handoff using the evidence already collected.
- **Unknown without No:** the safety check remains pending.
- **Any No:** PATCH enters the critical pathway.

## Critical operation: CRITICAL

When a confirmed safety check contains a No, PATCH immediately changes its behavior:

1. **Stops the interview.** New questions and routine replay answers are blocked.
2. **Displays the relevant emergency instructions.** Guidance comes from fixed application rules, independently of the interview.
3. **Creates a priority alert automatically.** The message captures the current state, confirmed checks, recorded findings, conversation, and displayed guidance.
4. **Keeps follow-up documentation available.** The crew can repeat the safety checks, record additional findings, and send a clinical handoff without finishing the interview.

The interface indicates that the interview is paused and that local emergency response takes priority. The dedicated presentation also shows a **Critical** badge.

Every critical guidance branch begins with:

> Activate the mission emergency response and call a trained crewmate now. Do not wait for an Earth reply.

### What the emergency instructions explain

The following describes the messages implemented in the prototype.

| Confirmed findings | Heading shown | What PATCH displays |
|---|---|---|
| Unresponsive and not breathing normally | **Unresponsive and not breathing normally** | Treat as suspected cardiac arrest; start CPR following the mission-approved procedure; obtain an AED if available and follow its prompts; continue until qualified responders take over or the mission procedure directs otherwise. Gasping is explicitly identified as abnormal breathing. |
| Unresponsive but breathing normally | **Unresponsive but breathing normally** | Maintain a clear airway according to training and mission procedures, consider possible injury before moving the person, stay with them, and repeatedly check breathing. Switch to the CPR/AED pathway if normal breathing stops or becomes gasping. |
| Responsive but not breathing normally | **Responsive with abnormal or difficult breathing** | Help the person adopt a position that makes breathing easier as safely permitted onboard, and monitor responsiveness and breathing. The message states that breathing difficulty alone does not establish cardiac arrest. Switch to the CPR/AED pathway if the person becomes unresponsive and is not breathing normally. |
| A No with the other finding unknown, or no usable current check during CRITICAL | **Check responsiveness and breathing now** | Activate the emergency response and verify responsiveness and breathing. The screen describes checking response to voice and a gentle shoulder tap while observing breathing, with a 10-second limit on the initial check. CPR/AED instructions are conditional on unresponsiveness together with abnormal breathing. |

The guidance includes an adult-simulation scope notice and source links. It does not specify a validated microgravity resuscitation technique. See [Safety guidance](docs/SAFETY_GUIDANCE.md) for the reference sources and clinical-review boundaries.

### Rechecks, findings, and critical handoffs

**Recheck responsiveness and breathing** saves updated answers, refreshes the instructions, and automatically sends another critical update.

**Record findings after immediate actions** opens the remaining observation controls. The operator can enter a result, source, quality, and observation time, or explicitly record that a result is unknown or unavailable. These entries are saved locally and included in subsequent outgoing snapshots.

The crew can send an incomplete but documented handoff through **Send critical update to Earth**, or **Review clinical handoff → Send handoff to Earth**, depending on the view. This manual handoff includes a structured report; it is separate from the automatic priority alert.

**CRITICAL does not clear automatically.** Even if a later check is Yes / Yes, PATCH keeps the critical state and the interview paused. In that situation it shows reassessment guidance and keeps the emergency response active. Sending a report, receiving it on Earth, or closing an episode does not establish medical recovery.

Reports already sent remain snapshots. Where available, **Send updated critical handoff** creates a new report containing later findings.

## Clinical handoff

PATCH builds the handoff locally from recorded evidence using **SBAR**:

| Section | Contents |
|---|---|
| **Situation** | Presenting complaint and current control state. |
| **Background** | Available mission and patient context. |
| **Assessment** | Recorded observations, without automatic diagnostic interpretation. |
| **Recommendation** | Human medical review; no automated treatment order. |

The full report also includes the interview transcript, safety checks, uncertainties, and event timeline. The UI presents either the SBAR sections or a document-style view with the complaint, history, observations, checks, and missing results.

Unavailable demographics, measurements, and observation times are not invented. A partial handoff preserves what is known and what remains missing.

## Communication with Earth

The current scenarios use a **15-minute one-way delay**.

| Event | Outgoing message |
|---|---|
| Start an episode | Initial alert with the complaint and initial context. |
| Request reassessment outside CRITICAL | Assessment update with the current evidence and pending safety check. |
| Enter CRITICAL or save a critical recheck | Priority update with the current checks and guidance. |
| Manually send a handoff | Clinical or critical update with an attached structured report. |

Ordinary interview answers update the onboard record; they do not each create a transmission. Each outgoing message preserves the information available when it was created.

The link panel shows whether messages are **queued**, **in transit**, or **delivered**. The **Earth inbox** contains delivered messages only. Priority messages use the same signal delay as other messages.

**Advance time** normally moves the simulation to the next pending arrival, or forward one minute when no milestone is pending. The dedicated replay also assigns predefined simulated times to selected actions. No wall-clock timer runs between clicks.

The backend supports queuing new messages while the link is unavailable; already transmitted messages still arrive on schedule. The default demo starts with the link up.

The initial alert can include a black-box attachment, but it contains **zero telemetry samples in the supplied recordings**. Reported vital signs are stored separately as observations.

The optional timing comparison is illustrative: its radio-only estimate assumes one question per round trip and immediate answers. It is not a measured performance result. All transmissions and the Earth inbox are local simulations.

## Data and project structure

Episodes, events, observations, and messages are stored in `data/patch_mvp.sqlite3`. Set `PATCH_DB_PATH` before launching the app to choose another database.

Enable **Technical details** to open saved episodes, inspect records, use a fixed clock step, or **Download JSON trace**. After sending a handoff, the operator can close the episode with a required note.

| File or directory | Responsibility |
|---|---|
| `app.py` | Main Streamlit interface and shared controls. |
| `case4_ui.py`, `case4.css`, `replay_click.html` | Dedicated demonstration presentation and replay interaction. |
| `controller.py` | Application commands, safety enforcement, observations, reports, and simulated time. |
| `core_hsm.py` | Deterministic assessment/critical state rules. |
| `emergency_guidance.py` | Safety questions, emergency messages, and reference links. |
| `config_scenarios.py`, `case_data/` | Recorded demonstration scenarios and source metadata. |
| `llm_anamnesis.py` | Interview backend abstraction and scripted behavior. |
| `contracts.py` | Validated data models. |
| `space_link_db.py` | SQLite storage and simulated message transport. |
| `requirements.txt` | Runtime dependencies. |
| `docs/` | Supporting architecture, safety, and demonstration documentation. |

## MVP scope

The current version replays supplied MedGemma interviews and uses deterministic safety rules. It does not include live model inference, real sensor integration, automated diagnosis, prescriptions, or a real flight-surgeon connection.

The clinical state is based on structured checks and events, not general interpretation of symptom text or vital-sign thresholds. The emergency content and examination descriptions require clinical and mission-specific review before any operational use.

Further documentation: [Architecture](docs/ARCHITECTURE.md) · [Safety guidance](docs/SAFETY_GUIDANCE.md) · [Scenario data](docs/SCENARIOS.md).

