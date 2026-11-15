"""Guided PATCH interface: one active clinical step and one clock button."""
import json
import os
from pathlib import Path
from uuid import uuid4
import streamlit as st
from config_scenarios import SCENARIOS, load_scenario, exam_catalog, simulated_exam
from contracts import format_met
from controller import Controller
from space_link_db import SpaceLinkDB
from emergency_guidance import guidance_for_answers

st.set_page_config(page_title="PATCH · Guided assessment", page_icon="🛰️", layout="centered")
ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("PATCH_DB_PATH", str(ROOT / "data" / "patch_mvp.sqlite3")))
STAGES = {"SAFETY": "1 · Safety check", "HISTORY": "2 · History",
          "VITALS": "3 · Vital signs", "EXAM": "4 · Examination",
          "REPORT": "5 · Handoff", "SENT": "Handoff sent", "CLOSED": "Episode closed",
          "CRITICAL": "Critical assessment"}


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


def packet_table(packets):
    return [{"Type": p["kind"], "Status": p["status"], "Created": format_met(p["created_at_sim"]),
             "Sent": format_met(p["sent_at_sim"]), "Arrival": format_met(p["arrives_at_sim"]),
             "Received": format_met(p["delivered_at_sim"])} for p in packets]


def show_safety_guidance(guidance, *, preview=False):
    st.error(guidance["title"])
    if preview:
        st.caption("Immediate guidance from the selected answers. Confirm both answers to save the check.")
    for number, step in enumerate(guidance["steps"], 1):
        st.markdown(f"{number}. {step}")
    st.caption(guidance["scope"])
    st.caption("Sources: " + " · ".join(f"[{item['title']}]({item['url']})" for item in guidance["sources"]))


def vital_check(controller, ep, *, critical=False):
    st.write("Answer both safety questions to continue. Neither answer is assumed.")
    prefix = f"safety:{ep['episode_id']}:{ep['state']['state_version']}:{critical}"
    labels = {"SELECT": "Select an answer", "YES": "Yes", "NO": "No", "UNKNOWN": "Unknown / unable to check"}
    consciousness = st.selectbox("1. Is the person responsive (responds to your voice or a gentle shoulder tap)?",
        list(labels), format_func=labels.get, key=f"{prefix}:responsive")
    st.caption("No means there is no response. If you cannot establish responsiveness, choose Unknown; do not assume unconsciousness.")
    breathing = st.selectbox("2. Is the person breathing normally (not just gasping)?",
        list(labels), format_func=labels.get, key=f"{prefix}:breathing")
    if "NO" in (consciousness, breathing):
        show_safety_guidance(guidance_for_answers(consciousness, breathing, critical=True), preview=True)
    elif "UNKNOWN" in (consciousness, breathing):
        st.warning("Ask a crewmate to check now. The interview stays blocked; unknown is not normal.")
    if st.button("Save emergency recheck" if critical else "Confirm both answers and continue", type="primary",
                 disabled="SELECT" in (consciousness, breathing), use_container_width=True, key=f"{prefix}:save"):
        act(controller, "critical_check" if critical else "check", "critical_check" if critical else "check",
            episode_id=ep["episode_id"], consciousness=consciousness, breathing=breathing)
    st.caption("Critical review remains active after a recheck; it does not restart the interview." if critical else
               "Both YES answers allow the interview. UNKNOWN keeps it blocked. Either NO activates the emergency pathway.")


def recorded_turn(controller, ep, workflow):
    step = workflow["current_step"]
    st.caption(f"Recorded case · turn {workflow['step_index'] + 1} of {workflow['total_steps']} · original English transcript")
    with st.chat_message("assistant"):
        st.write(step["question"])
    with st.expander("Preview the recorded answer"):
        st.write(step["answer"])
        st.caption("This answer has not yet been saved to the episode or included in any Earth message.")
    if st.button("Record the case answer and continue", type="primary", use_container_width=True):
        act(controller, "recorded_step", f"recorded:{ep['episode_id']}:{workflow['step_index']}",
            episode_id=ep["episode_id"], expected_step=workflow["step_index"], expected_version=ep["state"]["state_version"])
    st.caption("This replays a recorded turn. MedGemma is not running and free text is not interpreted.")


def manual_history(controller, ep, workflow):
    dialogue = controller.get_current_context(ep["episode_id"])["dialogue"]
    active = [e for e in dialogue if e["type"] == "patch_reply" and e["payload"].get("state_version") == ep["state"]["state_version"]]
    if active:
        with st.chat_message("assistant"):
            st.write(active[-1]["payload"]["text"])
    limit = workflow.get("history_limit", 5)
    st.caption(f"Question {min(workflow['step_index'] + 1, limit)} of {limit} · original scenario mock")
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
        st.caption(f"Available synthetic result: {scripted[0]} · {scripted[1]}")
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


def report_step(controller, ep):
    summary = controller.build_handoff(ep["episode_id"])
    st.write("The scripted assessment is complete. The handoff includes recorded information only.")
    st.caption("Missing blood pressure, temperature and respiratory rate remain unknown. Historical notebook diagnoses and recommendations are not reused.")
    with st.expander("Review the SBAR handoff"):
        st.json(summary)
    if st.button("Generate and send handoff to Earth", type="primary", use_container_width=True):
        act(controller, "handoff", "handoff", episode_id=ep["episode_id"])


def earth_inbox(controller, ep):
    with st.expander("Earth · received packets"):
        packets = controller.db.packets(ep["episode_id"], delivered_only=True)
        if not packets:
            st.info("Earth has not received any packets for this episode yet.")
        for packet in packets:
            st.markdown(f"**{packet['kind']}** · received {format_met(packet['delivered_at_sim'])}")
            st.caption(f"Created {format_met(packet['created_at_sim'])} · sent {format_met(packet['sent_at_sim'])}")
            st.json(packet["payload"], expanded=False)
        st.caption("Only delivered information is shown. Each packet retains its original contents.")


def main():
    st.title("🛰️ PATCH")
    st.caption("Guided assessment · fictional patients · no live LLM connection")
    with SpaceLinkDB(DB_PATH) as db:
        controller = Controller(db)
        with st.sidebar:
            st.subheader("Choose a case")
            choices = ["C01", "C02", "N02", "N04", "N06"]
            chosen = st.selectbox("Case", choices, format_func=lambda key: SCENARIOS[key]["title"])
            with st.form("new_episode"):
                st.caption("Cases 1 and 2 replay the supplied JSON recordings. Case 3 contained no files.")
                if st.form_submit_button("Start a new case", type="primary", use_container_width=True):
                    act(controller, "start", "start", scenario_id=chosen)
            episodes = db.list_episodes()
            if not episodes:
                st.info("Start a case to begin.")
                return
            ids = [e["episode_id"] for e in episodes]
            if st.session_state.get("episode_selector") not in ids:
                previous = db.get_setting("active_episode")
                st.session_state["episode_selector"] = previous if previous in ids else ids[0]
            eid = st.selectbox("Episode", ids, key="episode_selector")
            if db.get_setting("active_episode") != eid:
                db.set_setting("active_episode", eid)
            st.caption("Previous episodes are retained. Start a new case to restart its workflow.")
        ep = db.get_episode(eid)
        workflow = controller.get_workflow(eid)
        stage = workflow["display_stage"]
        st.subheader(SCENARIOS[ep["scenario_id"]]["title"])
        st.write(ep["opening"])
        a, b, c = st.columns(3)
        a.metric("Time", format_met(ep["clock"]["met_seconds"]))
        b.metric("Link", ep["clock"]["link_status"])
        c.metric("One-way delay", f"{ep['clock']['one_way_delay_seconds'] // 60} min")
        # The ONLY time-advance control. No jump buttons, trigger button or hidden timers.
        with st.form("clock_control"):
            minutes = st.number_input("Minutes to advance", min_value=1, max_value=2880, value=1, step=1)
            if st.form_submit_button("Advance time", use_container_width=True):
                act(controller, "advance", "advance", episode_id=eid,
                    target_time=ep["clock"]["met_seconds"] + minutes * 60)
        st.caption("Only this button advances the clock. It does not answer questions or complete assessment stages.")
        if workflow["recorded"]:
            st.caption("The 15-minute delay is a demo setting, not a notebook value. No continuous telemetry is fabricated.")
        st.divider()
        st.caption("Safety check → History → Vital signs → Examination → Handoff")
        progress = {"SAFETY": 0, "HISTORY": 1, "VITALS": 2, "EXAM": 3, "REPORT": 4, "SENT": 5, "CLOSED": 5}.get(stage, 0)
        st.progress(progress / 5)
        st.subheader(STAGES[stage])
        if stage == "SAFETY":
            st.warning(ep["state"]["reason"])
            vital_check(controller, ep)
        elif stage == "CRITICAL":
            st.error("The interview is suspended. Emergency assessment takes priority over the normal workflow.")
            guidance = controller.get_safety_guidance(eid)
            show_safety_guidance(guidance)
            if guidance["checked_at_sim"] is not None:
                st.caption(f"Based on the safety check saved at {format_met(guidance['checked_at_sim'])}.")
            with st.expander("Recheck responsiveness and breathing"):
                vital_check(controller, ep, critical=True)
            if st.checkbox("Record findings after immediate emergency actions", key=f"critical_findings:{eid}"):
                st.write("A · Speech and airway. B · Breathing effort and available readings. C · Circulatory signs.")
                exam_step(controller, ep, workflow)
            if st.button("Send a critical update", type="primary"):
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
        elif stage == "SENT":
            st.success("The handoff is queued for delivery. Receipt depends on the clock and link status.")
            st.caption("Advance the clock to deliver it to Earth. Monitoring continues in the original scenarios.")
        elif stage == "CLOSED":
            st.info("Episode closed. You can review its records and advance the clock to complete deliveries.")
        # Safety remains available after a successful check, without skipping the wizard.
        if stage not in ("SAFETY", "CRITICAL", "CLOSED"):
            if st.button("Request human review / repeat safety check"):
                act(controller, "urgent_review", "review", episode_id=eid)
        st.divider()
        with st.expander("Onboard record"):
            context = controller.get_current_context(eid)
            st.write("**Recorded conversation**")
            for event in context["dialogue"]:
                st.write(f"{format_met(event['t_sim'])} · {'PATCH' if event['type'] == 'patch_reply' else 'Crew'}")
                st.write(event["payload"]["text"])
            st.write("**Recorded measurements and examinations**")
            rows = [{"Metric": o["metric"], "Result": str(o["value"]) if o["value"] is not None else "—",
                     "Unit": o["unit"], "Source": o["source"], "Status": o["quality"],
                     "Observed": format_met(o["observed_at_sim"]), "Entered": format_met(o["entered_at_sim"])}
                    for o in context["observations"]]
            if rows:
                st.dataframe(rows, hide_index=True, use_container_width=True)
            else:
                st.caption("No results have been recorded yet.")
            if context["current_telemetry"]:
                st.write("**Latest simulated sensor readings**")
                st.dataframe(context["current_telemetry"], hide_index=True, use_container_width=True)
            st.write("**Outgoing queue**")
            st.dataframe(packet_table(db.packets(eid)), hide_index=True, use_container_width=True)
        earth_inbox(controller, ep)
        with st.expander("Export and case details"):
            st.download_button("Download JSON trace", json.dumps(controller.export_trace(eid), ensure_ascii=False, indent=2),
                file_name=f"PATCH-{eid}.json", mime="application/json")
            for note in load_scenario(ep["scenario_id"])["pending"]:
                st.caption(note)
            if ep["report_ready"] and not ep["closed"]:
                with st.form(f"close:{eid}"):
                    note = st.text_input("Closure note")
                    if st.form_submit_button("Close episode"):
                        act(controller, "close", "close", episode_id=eid, note=note)
        st.caption("Demonstration prototype. Case data do not constitute a validated clinical protocol.")


if __name__ == "__main__":
    main()
