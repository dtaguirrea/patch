"""Presentation-focused PATCH UI; clinical state and evidence stay in the controller."""
import json
import os
from pathlib import Path
from uuid import uuid4

import streamlit as st
from config_scenarios import SCENARIOS, load_scenario, exam_catalog, simulated_exam
from controller import Controller
from space_link_db import SpaceLinkDB
from case_ui import case_screen, app_style

st.set_page_config(page_title="PATCH · Care beyond Earth", page_icon="🛰️", layout="wide", initial_sidebar_state="collapsed")
ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("PATCH_DB_PATH", str(ROOT / "data" / "patch_mvp.sqlite3")))
CASE_NAMES = {key: value["title"] for key, value in SCENARIOS.items()}
CASE_NOTES = {"C01": "Abdominal symptoms, recorded vital signs and an Earth handoff.",
              "C02": "A shorter interview with flank pain and reported findings.",
              "C03": "Lightheadedness, reported vital signs and an abdominal examination.",
              "C04": "Palpitations followed by a change in symptoms and a safety recheck."}


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


def main():
    app_style()
    with SpaceLinkDB(DB_PATH) as db:
        controller = Controller(db)
        with st.sidebar:
            st.markdown('<div class="eyebrow">DEMO CONTROL</div>', unsafe_allow_html=True)
            st.subheader("Choose a case")
            chosen = st.selectbox("Case", list(CASE_NAMES), index=list(CASE_NAMES).index("C04"), format_func=CASE_NAMES.get, label_visibility="collapsed")
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
            st.title("PATCH")
            st.header("Earth is 15 minutes away by radio.")
            st.write("Choose a recorded case to assess the crew member and send a handoff to Earth.")
            for scenario_id, title in CASE_NAMES.items():
                with st.container(border=True):
                    st.subheader(title)
                    st.caption(CASE_NOTES[scenario_id])
                    if st.button(f"Start {title.split(' · ')[0]}", key=f"start:{scenario_id}"):
                        act(controller, "start", "start", scenario_id=scenario_id)
            st.caption("Demonstration prototype · not for clinical use.")
            return
        eid = st.session_state["episode_selector"]
        if db.get_setting("active_episode") != eid:
            db.set_setting("active_episode", eid)
        ep = db.get_episode(eid)
        workflow = controller.get_workflow(eid)
        case_screen(controller, ep, workflow, db.packets(eid), act, next_clock_target, duration,
                    show_safety_guidance, exam_step, technical)
        if technical:
            technical_details(controller, ep)


if __name__ == "__main__":
    main()
