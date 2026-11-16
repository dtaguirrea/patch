"""Presentation-focused PATCH UI; clinical state and evidence stay in the controller."""
import json
import os
from html import escape
from pathlib import Path
from uuid import uuid4

import streamlit as st
from config_scenarios import SCENARIOS, load_scenario, exam_catalog, simulated_exam
from contracts import format_met
from controller import Controller
from space_link_db import SpaceLinkDB
from emergency_guidance import guidance_for_answers

st.set_page_config(page_title="PATCH · Care beyond Earth", page_icon="🛰️", layout="wide")
ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("PATCH_DB_PATH", str(ROOT / "data" / "patch_mvp.sqlite3")))
PHASES = ["SAFETY", "HISTORY", "VITALS", "EXAM", "REPORT"]
STAGES = {"SAFETY": "Safety check", "HISTORY": "Patient interview", "VITALS": "Vital signs",
          "EXAM": "Examination", "REPORT": "Clinical handoff", "SENT": "Handoff sent",
          "CLOSED": "Case closed", "CRITICAL": "Emergency response"}
CASE_NAMES = {key: value["title"] for key, value in SCENARIOS.items()}
CASE_NOTES = {"C01": "Abdominal symptoms, recorded vital signs and an Earth handoff.",
              "C02": "A shorter interview with flank pain and reported findings.",
              "C03": "Lightheadedness, reported vital signs and an abdominal examination.",
              "C04": "Palpitations followed by a change in symptoms and a safety recheck."}


def style():
    st.markdown("""<style>
    .block-container {max-width:1180px; padding-top:2rem; padding-bottom:2rem;}
    [data-testid="stSidebar"] {border-right:1px solid #233348;}
    [data-testid="stSidebar"] .block-container {padding-top:2rem;}
    h1 {font-size:2.5rem !important; letter-spacing:.09em; padding-bottom:0 !important;}
    h2 {font-size:1.65rem !important;} h3 {font-size:1.2rem !important;}
    [data-testid="stMetricValue"] {font-size:1.45rem;}
    [data-testid="stChatMessage"] {padding:1rem; border:1px solid #2b3d53;}
    .eyebrow {font-size:.72rem; color:#7ee4d2; letter-spacing:.14em; font-weight:700; margin-bottom:.5rem;}
    .subtitle {color:#a9bbcc; margin:0 0 1.6rem;}
    .steps {display:flex; gap:6px; margin:0 0 1.3rem; flex-wrap:wrap;}
    .step {flex:1; min-width:75px; padding:9px 8px; border-top:3px solid #2b3b51;
           color:#92a5ba; font-size:.78rem;}
    .step.active {border-color:#55d9c0; color:#e8fff9; background:#183530; border-radius:0 0 7px 7px;}
    .step.done {border-color:#437f78; color:#b5dad2;}
    .case-title {font-size:1.65rem; font-weight:650; margin:0 0 .3rem;}
    .intro {color:#a9bbcc; font-size:1rem; margin-bottom:1.2rem;}
    @media(max-width:700px) {.block-container {padding-top:1.5rem;} .step {min-width:60px;}}
    </style>""", unsafe_allow_html=True)


def act(controller, action, key, **kwargs):
    token_key = f"command:{key}"
    token = st.session_state.setdefault(token_key, uuid4().hex)
    try:
        result = controller.command(action, command_id=token, **kwargs)
    except (ValueError, KeyError) as exc:
        st.error(str(exc))
        return
    st.session_state[token_key] = uuid4().hex
    if action == "start":
        st.session_state["episode_selector"] = result
    st.rerun()


def show_safety_guidance(guidance, *, preview=False):
    st.error(guidance["title"])
    for number, step in enumerate(guidance["steps"], 1):
        st.markdown(f"{number}. {step}")
    if preview:
        st.caption("Confirm both answers to save this check. Do not delay immediate help.")
    st.caption("Adult simulation · follow mission-approved emergency procedures.")
    with st.expander("Guidance scope and sources"):
        st.write(guidance["scope"])
        for item in guidance["sources"]:
            st.markdown(f"[{item['title']}]({item['url']})")


def vital_check(controller, ep, *, critical=False):
    st.caption("Check both before continuing.")
    prefix = f"safety:{ep['episode_id']}:{ep['state']['state_version']}:{critical}"
    labels = {"SELECT": "Choose an answer", "YES": "Yes", "NO": "No", "UNKNOWN": "Unable to check"}
    consciousness = st.selectbox("Is the person responsive?", list(labels), format_func=labels.get,
        key=f"{prefix}:responsive", help="Check for a response to your voice or a gentle shoulder tap. No means no response; choose Unable to check if uncertain.")
    breathing = st.selectbox("Is the person breathing normally (not just gasping)?", list(labels), format_func=labels.get,
        key=f"{prefix}:breathing", help="Gasping is not normal breathing. Choose Unable to check if uncertain.")
    if "NO" in (consciousness, breathing):
        show_safety_guidance(guidance_for_answers(consciousness, breathing, critical=True), preview=True)
    elif "UNKNOWN" in (consciousness, breathing):
        st.warning("Ask a crewmate to check. The interview stays paused until both answers are Yes.")
    if st.button("Save emergency recheck" if critical else "Confirm safety check", type="primary",
                 disabled="SELECT" in (consciousness, breathing), use_container_width=True, key=f"{prefix}:save"):
        act(controller, "critical_check" if critical else "check", "critical_check" if critical else "check",
            episode_id=ep["episode_id"], consciousness=consciousness, breathing=breathing)
    if critical:
        st.caption("The interview remains paused after an emergency recheck.")


def recorded_turn(controller, ep, workflow):
    step = workflow["current_step"]
    st.caption(f"Step {workflow['step_index'] + 1} of {workflow['total_steps']} · recorded MedGemma case")
    with st.chat_message("assistant", avatar="🛰️"):
        st.write(step["question"])
    with st.chat_message("user", avatar="👤"):
        st.caption("DEMO ANSWER · NOT YET RECORDED")
        st.write(step["answer"])
    if st.button("Use demo answer →", type="primary", use_container_width=True):
        act(controller, "recorded_step", f"recorded:{ep['episode_id']}:{workflow['step_index']}",
            episode_id=ep["episode_id"], expected_step=workflow["step_index"], expected_version=ep["state"]["state_version"])


def manual_history(controller, ep, workflow):
    dialogue = controller.get_current_context(ep["episode_id"])["dialogue"]
    active = [e for e in dialogue if e["type"] == "patch_reply" and e["payload"].get("state_version") == ep["state"]["state_version"]]
    if active:
        with st.chat_message("assistant"):
            st.write(active[-1]["payload"]["text"])
    limit = workflow.get("history_limit", 5)
    st.caption(f"Question {min(workflow['step_index'] + 1, limit)} of {limit} · scripted interview")
    with st.form(f"history:{ep['episode_id']}", clear_on_submit=True):
        response = st.text_area("Astronaut response", max_chars=8000)
        if st.form_submit_button("Save response and continue", type="primary", use_container_width=True):
            act(controller, "chat", "history", episode_id=ep["episode_id"], text=response,
                expected_version=ep["state"]["state_version"])


def exam_step(controller, ep, workflow):
    eid = ep["episode_id"]
    stage = workflow["display_stage"]
    catalog = exam_catalog(ep["scenario_id"])
    remaining = controller.phase_remaining_exams(eid)
    if not remaining:
        if stage == "CRITICAL":
            st.success("Assessment results recorded.")
            return
        st.info("This stage is documented." if controller.phase_exam_ids(eid) else "No additional examinations are configured for this scenario.")
        if st.button("Continue to the next stage", type="primary", use_container_width=True):
            act(controller, "complete_phase", "complete_phase", episode_id=eid, expected_stage=stage)
        return
    # One requested measurement at a time; recording UNKNOWN/UNAVAILABLE is explicit.
    metric = remaining[0]
    st.write(f"**Next observation: {catalog[metric]['label']}** · {catalog[metric]['unit']}")
    pending = next((r for r in controller.pending_exams(eid) if r["payload"]["exam_id"] == metric), None)
    if pending is None:
        if st.button("Request this observation", type="primary", use_container_width=True):
            act(controller, "request_exam", "request_exam", episode_id=eid, exam_id=metric)
        return
    scripted = simulated_exam(ep["scenario_id"], metric, ep["clock"]["met_seconds"], deteriorated=ep["deteriorated"])
    if scripted is not None:
        st.caption(f"Demo result: {scripted[0]} · {scripted[1]}")
        if st.button("Record the scripted result", type="primary", use_container_width=True):
            act(controller, "record_exam", "script_exam", episode_id=eid, request_id=pending["event_id"], use_script=True)
    with st.expander("Enter a result or record its unavailability", expanded=scripted is None):
        with st.form(f"exam:{pending['event_id']}"):
            value = st.text_input("Result", max_chars=1500)
            source = st.selectbox("Source", ["exam_entry", "crew_reported"])
            quality = st.selectbox("Data quality", ["valid", "unknown", "unavailable", "denied", "suspect"])
            timing = st.selectbox("Observation time", ["Now", "Minutes earlier", "Unknown"])
            minutes_ago = st.number_input("Minutes earlier (if applicable)", min_value=0, max_value=525600, value=0)
            if st.form_submit_button("Save observation"):
                observed = None if timing == "Unknown" else ep["clock"]["met_seconds"] - (minutes_ago * 60 if timing == "Minutes earlier" else 0)
                act(controller, "record_exam", "manual_exam", episode_id=eid, request_id=pending["event_id"],
                    value=value, source=source, quality=quality, observed_at_sim=observed)


def observation_rows(observations):
    return [{"Observation": item["metric"].replace("_", " ").capitalize(),
             "Result": f"{item['value']} {item['unit']}".strip() if item["value"] is not None else "Unknown",
             "Quality": item["quality"].replace("_", " ")} for item in observations]


def readable_handoff(summary, *, include_history=True):
    """Render recorded evidence only, including when viewing a delivered snapshot."""
    sbar = summary["sbar"]
    st.markdown("**Situation**")
    st.write(sbar["Situation"]["reason"])
    st.markdown("**Background**")
    background = sbar["Background"]
    details = [f"{label}: {background[key]}" for key, label in
               (("mission", "Mission"), ("age", "Age"), ("sex", "Sex"), ("role", "Role"))
               if key in background]
    st.write(" · ".join(details) if details else "See the recorded patient history.")
    if background.get("record_status"):
        st.caption("No demographic or prior-history record was supplied. Reported history remains in the transcript.")
    else:
        for key, label in (("history", "History"), ("allergies", "Allergies"), ("regular_medications", "Medication")):
            value = background.get(key)
            if value:
                st.write(f"{label}: {', '.join(value) if isinstance(value, list) else value}")
    st.markdown("**Assessment · recorded findings**")
    rows = observation_rows(summary["observations"])
    if rows:
        st.dataframe(rows, hide_index=True, use_container_width=True)
    else:
        st.caption("No examination results recorded.")
    if sbar["Assessment"].get("telemetry"):
        st.caption("Latest simulated sensor readings")
        for item in sbar["Assessment"]["telemetry"]:
            st.write(f"{item['metric'].replace('_', ' ').capitalize()}: {item['value']} {item['unit']}")
    st.caption("Reported findings are not a diagnosis. Missing measurements remain unknown.")
    st.markdown("**Recommendation**")
    st.write("Review by the medical team on Earth. No automated treatment order.")
    if include_history:
        with st.expander("Patient history and uncertainties"):
            for event in summary["transcript"]:
                if event["type"] in ("opening_message", "patient_message", "crew_statement"):
                    st.write("• " + event["payload"]["text"])
            for uncertainty in summary["uncertainties"]:
                st.caption(uncertainty)


def report_step(controller, ep):
    if controller.get_workflow(ep["episode_id"]).get("recording_ended_with_recheck"):
        st.info("The source recording ends at the safety recheck. Send the available findings for human review; no completed cardiac examination was supplied.")
    readable_handoff(controller.build_handoff(ep["episode_id"]))
    if st.button("Send handoff to Earth →", type="primary", use_container_width=True):
        act(controller, "handoff", "handoff", episode_id=ep["episode_id"])


def next_clock_target(ep, packets):
    """One explicit click reaches the next simulation milestone; never auto-advance."""
    now = ep["clock"]["met_seconds"]
    upcoming = [p["arrives_at_sim"] for p in packets if p["status"] == "IN_TRANSIT" and p["arrives_at_sim"] > now]
    if not ep["closed"]:
        upcoming += [item["at"] for item in load_scenario(ep["scenario_id"])["schedule"]
                     if item["id"] not in ep["handled_schedule"] and item["at"] > now]
    return min(upcoming) if upcoming else now + 60


def duration(seconds):
    hours, remainder = divmod(max(0, seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    return " ".join(part for part in (f"{hours} h" if hours else "", f"{minutes} min" if minutes else "",
                                     f"{secs} s" if secs else "") if part) or "0 min"


def earth_panel(controller, ep, packets, technical):
    now = ep["clock"]["met_seconds"]
    with st.container(border=True):
        st.markdown('<div class="eyebrow">SPACE → EARTH</div>', unsafe_allow_html=True)
        st.subheader("Mission link")
        if ep["clock"]["link_status"] == "UP":
            st.caption(f"● Connected · {duration(ep['clock']['one_way_delay_seconds'])} one-way delay")
        else:
            st.warning("Link unavailable. New messages stay onboard until reconnection.")
        latest = packets[-1] if packets else None
        if latest:
            label = {"INITIAL_ALERT": "Initial alert", "CLINICAL_UPDATE": "Clinical handoff", "CRITICAL_UPDATE": "Critical update"}[latest["kind"]]
            st.markdown(f"**{label}**")
            if latest["status"] == "DELIVERED":
                st.success("Received on Earth")
                st.caption(f"Arrived at {format_met(latest['delivered_at_sim'])}")
            elif latest["status"] == "IN_TRANSIT":
                st.info(f"In transit · {duration(latest['arrives_at_sim'] - now)} remaining")
            else:
                st.info("Queued onboard")
        st.metric("Mission elapsed time", format_met(now))
        target = next_clock_target(ep, packets)
        if technical:
            custom = st.checkbox("Use a fixed time step", key=f"fixed:{ep['episode_id']}")
            if custom:
                minutes = st.number_input("Minutes per click", min_value=1, max_value=2880, value=1,
                                          key=f"minutes:{ep['episode_id']}")
                target = now + minutes * 60
        if st.button(f"Advance time (+{duration(target - now)})", use_container_width=True):
            act(controller, "advance", "advance", episode_id=ep["episode_id"], target_time=target)
        st.caption("Simulation pauses between clicks.")
        delivered = [p for p in packets if p["status"] == "DELIVERED"]
        with st.expander(f"Earth inbox · {len(delivered)} received"):
            if not delivered:
                st.caption("No messages received yet.")
            for packet in reversed(delivered):
                title = {"INITIAL_ALERT": "Initial alert", "CLINICAL_UPDATE": "Clinical handoff", "CRITICAL_UPDATE": "Critical update"}[packet["kind"]]
                st.markdown(f"**{title} · {format_met(packet['delivered_at_sim'])}**")
                payload = packet["payload"]
                if payload.get("summary"):
                    readable_handoff(payload["summary"], include_history=False)
                else:
                    st.write(payload["opening"])
                    if payload["state"]["hsm_state"] == "CRITICAL":
                        st.caption("Emergency response active onboard at the time of sending.")
                    else:
                        st.caption("Assessment started. Awaiting a clinical handoff.")
                st.divider()


def technical_details(controller, ep):
    with st.expander("Technical record and export"):
        context = controller.get_current_context(ep["episode_id"])
        st.caption(f"Episode: {ep['episode_id']}")
        st.json(context, expanded=False)
        st.json(controller.db.packets(ep["episode_id"]), expanded=False)
        st.download_button("Download JSON trace", json.dumps(controller.export_trace(ep["episode_id"]), ensure_ascii=False, indent=2),
                           file_name=f"PATCH-{ep['episode_id']}.json", mime="application/json")
        for note in load_scenario(ep["scenario_id"])["pending"]:
            st.caption(note)
        if ep["report_ready"] and not ep["closed"]:
            with st.form(f"close:{ep['episode_id']}"):
                note = st.text_input("Closure note")
                if st.form_submit_button("Close case"):
                    act(controller, "close", "close", episode_id=ep["episode_id"], note=note)


def stage_progress(stage):
    current = PHASES.index(stage) if stage in PHASES else 5
    labels = ["Safety", "Interview", "Vitals", "Exam", "Handoff"]
    markup = '<div class="steps">'
    for i, label in enumerate(labels):
        state = "active" if i == current else "done" if i < current else ""
        markup += f'<div class="step {state}">{i + 1} · {label}</div>'
    st.markdown(markup + '</div>', unsafe_allow_html=True)


def main():
    style()
    st.title("PATCH")
    st.markdown('<p class="subtitle">Care beyond Earth. Guided onboard assessment, connected to mission support.</p>', unsafe_allow_html=True)
    with SpaceLinkDB(DB_PATH) as db:
        controller = Controller(db)
        with st.sidebar:
            st.markdown('<div class="eyebrow">DEMO CONTROL</div>', unsafe_allow_html=True)
            st.subheader("Choose a case")
            chosen = st.selectbox("Case", list(CASE_NAMES), format_func=CASE_NAMES.get, label_visibility="collapsed")
            st.caption(CASE_NOTES[chosen])
            if st.button("Start case →", type="primary", use_container_width=True):
                act(controller, "start", "start", scenario_id=chosen)
            st.divider()
            technical = st.toggle("Technical details", value=False)
            episodes = [episode for episode in db.list_episodes() if episode["scenario_id"] in SCENARIOS]
            ids = [e["episode_id"] for e in episodes]
            if episodes and st.session_state.get("episode_selector") not in ids:
                previous = db.get_setting("active_episode")
                st.session_state["episode_selector"] = previous if previous in ids else ids[0]
            if technical and episodes:
                names = {e["episode_id"]: f"{CASE_NAMES.get(e['scenario_id'], e['scenario_id'])} · {len(episodes) - i}"
                         for i, e in enumerate(episodes)}
                resume = st.selectbox("Saved cases", ids, format_func=names.get,
                                      index=ids.index(st.session_state["episode_selector"]))
                if st.button("Open saved case"):
                    st.session_state["episode_selector"] = resume
                    db.set_setting("active_episode", resume)
                    st.rerun()
            st.caption("Demo mode · fictional cases\n\nRecorded MedGemma interviews · no live AI")
        if not episodes:
            with st.container(border=True):
                st.markdown('<div class="eyebrow">ONBOARD CARE, STEP BY STEP</div>', unsafe_allow_html=True)
                st.header("Ready when the crew needs it.")
                st.write("Check immediate safety, gather the story and send a structured handoff to Earth.")
                st.info("Choose a case in the sidebar, then select Start case.")
            st.caption("Demonstration prototype · not for clinical use.")
            return
        eid = st.session_state["episode_selector"]
        if db.get_setting("active_episode") != eid:
            db.set_setting("active_episode", eid)
        ep = db.get_episode(eid)
        workflow = controller.get_workflow(eid)
        stage = workflow["display_stage"]
        packets = db.packets(eid)
        main_col, link_col = st.columns([1.9, 1], gap="large")
        with main_col:
            st.markdown(f'<div class="case-title">{escape(CASE_NAMES[ep["scenario_id"]])}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="intro">“{escape(ep["opening"])}”</div>', unsafe_allow_html=True)
            if stage != "CRITICAL":
                stage_progress(stage)
            with st.container(border=True):
                st.subheader("Safety recheck" if stage == "SAFETY" and workflow.get("recording_ended_with_recheck") else STAGES[stage])
                if stage == "SAFETY":
                    if workflow.get("recording_ended_with_recheck"):
                        st.warning("Condition changed. Repeat both safety checks before continuing.")
                        dialogue = controller.get_current_context(eid)["dialogue"]
                        last_report = next((event for event in reversed(dialogue) if event["type"] == "patient_message"), None)
                        if last_report:
                            st.write(last_report["payload"]["text"])
                    vital_check(controller, ep)
                elif stage == "CRITICAL":
                    st.caption("Interview paused · local emergency response takes priority")
                    show_safety_guidance(controller.get_safety_guidance(eid))
                    if st.checkbox("Recheck responsiveness and breathing", key=f"emergency_recheck:{eid}"):
                        vital_check(controller, ep, critical=True)
                    if st.checkbox("Record findings after immediate actions", key=f"critical_findings:{eid}"):
                        exam_step(controller, ep, workflow)
                    if st.button("Send critical update to Earth", type="primary", use_container_width=True):
                        act(controller, "handoff", "critical_report", episode_id=eid)
                elif stage in ("HISTORY", "VITALS", "EXAM"):
                    if workflow["recorded"]:
                        recorded_turn(controller, ep, workflow)
                    elif stage == "HISTORY":
                        manual_history(controller, ep, workflow)
                    else:
                        exam_step(controller, ep, workflow)
                elif stage == "REPORT":
                    report_step(controller, ep)
                elif stage in ("SENT", "CLOSED"):
                    reports = [p for p in packets if p["payload"].get("summary")]
                    latest_report = reports[-1] if reports else None
                    if latest_report and latest_report["status"] == "DELIVERED":
                        st.success("The medical team on Earth has received the handoff.")
                        st.write("The recorded assessment is ready for human review.")
                    else:
                        st.success("Handoff saved and sent to the mission link.")
                        st.write("Advance time to follow its delivery to Earth.")
                    if latest_report:
                        with st.expander("View handoff"):
                            readable_handoff(latest_report["payload"]["summary"], include_history=False)
                if stage not in ("SAFETY", "CRITICAL", "CLOSED"):
                    st.divider()
                    if st.button("Request urgent review", help="Pause the interview and activate emergency reassessment."):
                        act(controller, "urgent_review", "review", episode_id=eid)
            context = controller.get_current_context(eid)
            if context["observations"] and stage not in ("REPORT", "SENT", "CLOSED"):
                with st.expander("Recorded findings"):
                    st.dataframe(observation_rows(context["observations"]), hide_index=True, use_container_width=True)
                    st.caption("Reported observations may have unknown measurement times.")
        with link_col:
            earth_panel(controller, ep, packets, technical)
        if technical:
            technical_details(controller, ep)
        st.caption("Demonstration prototype · not for clinical use.")


if __name__ == "__main__":
    main()
