"""Recorded case presentation. Clinical decisions and packets come from the controller."""
from html import escape
from pathlib import Path

import streamlit as st

from config_scenarios import SCENARIOS
from contracts import format_met
from emergency_guidance import guidance_for_answers


def app_style():
    css = Path(__file__).with_name("case_ui.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def markup(html):
    st.markdown(html, unsafe_allow_html=True)


def bubble_html(text, crew=False, changed=False):
    label = "Astronaut" if crew else "MedGemma · recorded"
    classes = "crew" if crew else "model"
    return (f'<div class="turn {classes}"><small>{label}</small>'
            f'<div class="bubble {"changed" if changed else ""}">{escape(" ".join(text.split()))}</div></div>')


def conversation(dialogue, changed=False, playback=False):
    bubbles = [bubble_html(event["payload"]["text"], crew=event["type"] != "patch_reply",
                           changed=changed and i == len(dialogue) - 1)
               for i, event in enumerate(dialogue)]
    marker = f' data-replay-turn="{escape(dialogue[-1]["event_id"])}"' if playback else ""
    markup(f'<div class="conversation" role="log" aria-label="Recorded interview" tabindex="0"{marker}>'
           '<div>' + "".join(bubbles) + '</div></div>')


def safety(controller, ep, act, recheck=False, critical=False, suggested=False):
    prefix = f"{ep['episode_id']}:{ep['state']['state_version']}"
    labels = {"YES": "Yes", "NO": "No", "UNKNOWN": "Not sure"}
    with st.container(key="safety_card", border=True):
        if suggested:
            markup('<div class="signal">MedGemma suggested a safety recheck</div>')
        st.subheader("Condition changed. Answer both again." if recheck else "First, two safety questions")
        st.caption("Simulated crew response · check the astronaut before continuing." if recheck
                   else "Record what the crew observes now.")
        answers = [st.segmented_control(question, list(labels), format_func=labels.get,
                                        key=f"{prefix}:{index}")
                   for index, question in enumerate(("Is the person responsive?",
                       "Is the person breathing normally (not just gasping)?"))]
        if "NO" in answers:
            guidance = guidance_for_answers(*answers, critical=True)
            st.error(guidance["title"])
            for step in guidance["steps"]:
                st.write(step)
        elif "UNKNOWN" in answers:
            st.warning("Ask a crewmate to check. The interview remains paused.")
        if st.button("Confirm recheck" if recheck else "Confirm safety check",
                     disabled=None in answers, type="primary"):
            timing = {} if critical else {"replay_at": ep["clock"]["met_seconds"] + 35 if recheck else 20, "defer_question": True}
            act(controller, "critical_check" if critical else "check", prefix,
                episode_id=ep["episode_id"], consciousness=answers[0], breathing=answers[1], **timing)


def report_sheet(summary, title):
    situation = summary["sbar"]["Situation"]
    def rows(values):
        return "".join(f"<li>{escape(str(v))}</li>" for v in values) or "<li>None recorded</li>"
    history = [e["payload"]["text"] for e in summary["transcript"] if e["type"] == "patient_message"]
    findings = [f"{o['metric']} · {o['value']} {o['unit']} · {o['source']}" for o in summary["observations"]]
    checks = [f"{format_met(e['t_sim'])} · responsive: {e['payload']['consciousness']} · "
              f"breathing normally: {e['payload']['breathing']}" for e in summary["checks"]]
    missing = [u for u in summary["uncertainties"] if u.startswith("No supplied result")]
    state = escape(situation["control_state"]["hsm_state"])
    stamp = "stamp critical-stamp" if state == "CRITICAL" else "stamp"
    markup(f'<article class="paper"><header>Clinical handoff · {escape(title)}'
           f'<small>{format_met(summary["generated_at_sim"])}</small></header>'
           f'<b class="{stamp}">{state}</b><h4>Chief complaint</h4><p>{escape(situation["reason"])}</p>'
           f'<h4>History from the interview</h4><ul>{rows(history)}</ul>'
           f'<div class="sheet-grid"><section><h4>Recorded observations</h4><ul>{rows(findings)}</ul></section>'
           f'<section><h4>Safety checks · crew entries</h4><ul>{rows(checks)}</ul></section></div>'
           f'<h4>Unavailable at handoff</h4><ul>{rows(missing)}</ul>'
           '<footer>Recorded evidence for human review · simulation</footer></article>')


def packet_label(packet):
    if packet["payload"].get("summary"):
        return "Clinical handoff"
    if packet["kind"] == "INITIAL_ALERT" and "black_box_snapshot" in packet["payload"]:
        return "Initial alert + black box"
    return {"INITIAL_ALERT":"Initial alert","CRITICAL_UPDATE":"Priority alert",
            "CLINICAL_UPDATE":"Assessment update"}[packet["kind"]]


def link_panel(ep, packets, act, controller, next_target, duration, technical):
    clock = ep["clock"]
    now = clock["met_seconds"]
    delay = clock["one_way_delay_seconds"]
    with st.container(border=True, key="mission_link"):
        st.caption("Link to Earth")
        markup(f'<strong class="bigtime">{duration(delay)}</strong><small>one-way delay</small>')
        current = packets[-1] if packets else None
        fraction = 0
        if current and current["sent_at_sim"] is not None:
            transit = current["arrives_at_sim"] - current["sent_at_sim"]
            fraction = min(1, max(0, (now-current["sent_at_sim"])/transit)) if transit else 1
        markup('<div class="ends"><span>Ship</span><span>Earth</span></div>'
               f'<div class="orbit"><i style="left:{fraction*100:.2f}%"></i></div>')
        if clock["link_status"] != "UP":
            st.warning("Link unavailable")
        for p in reversed(packets):
            label = packet_label(p)
            status = p["status"]
            if status == "IN_TRANSIT":
                detail = "arrives in " + duration(p["arrives_at_sim"] - now)
            elif status == "DELIVERED":
                detail = "received " + format_met(p["delivered_at_sim"])
            else:
                detail = "queued onboard"
            st.caption(f"{label} · {detail}")
        target = next_target(ep, packets)
        if technical and st.checkbox("Use a fixed time step"):
            target = now + 60 * st.number_input("Minutes per click", 1, 2880, 1)
        if st.button(f"Advance time (+{duration(target-now)})"):
            act(controller, "advance", "advance", episode_id=ep["episode_id"], target_time=target)
        delivered = [p for p in packets if p["status"] == "DELIVERED"]
        with st.expander(f"Earth inbox · {len(delivered)} received"):
            if not delivered:
                st.caption("No messages received yet.")
            for p in reversed(delivered):
                st.caption(f"{packet_label(p)} · {format_met(p['delivered_at_sim'])}")
                if "black_box_snapshot" in p["payload"]:
                    count = len(p["payload"]["black_box_snapshot"])
                    st.caption(f"Black box · {count} telemetry samples attached")
                if p["payload"].get("summary"):
                    report_sheet(p["payload"]["summary"], SCENARIOS[ep["scenario_id"]]["title"])
                else:
                    st.write(p["payload"]["opening"])
                    st.write(p["payload"]["state"]["reason"])


def comparison(packet, delay, duration):
    summary = packet["payload"]["summary"]
    questions = sum(e["type"] == "patient_message" for e in summary["transcript"])
    radio_total = delay * (1 + 2 * questions)
    delivered = packet["status"] == "DELIVERED"
    arrival = packet["delivered_at_sim"] if delivered else packet["arrives_at_sim"]
    scale = max(arrival or 0, radio_total, 1)
    st.header("Time to get the findings to Earth")
    if delivered:
        st.caption("Earth has received the clinical handoff.")
    elif arrival is not None:
        st.caption(f"Handoff sent at {format_met(packet['sent_at_sim'])} · in transit to Earth.")
    else:
        st.caption("Handoff queued onboard. Arrival time will be available when the link sends it.")
    left, right = st.columns(2)
    for col, label, value, note, klass in [
        (left, "With PATCH", arrival, "Received on Earth" if delivered else "Estimated arrival from case start", "light"),
        (right, "Without PATCH · radio only", radio_total,
         f"One alert + {questions} separate round trips", "dark")]:
        with col:
            markup(f'<section class="result {klass}"><small>{label}</small>'
                   f'<strong>{duration(value) if value is not None else "Pending"}</strong><small>{note}</small></section>')
    def segment(seconds, label, color):
        return (f'<span title="{escape(label)}" style="width:{100*seconds/scale:.3f}%;'
                f'background:{color}"></span>')
    onboard = packet["sent_at_sim"]
    if onboard is not None and arrival is not None:
        trip = arrival - onboard
        markup('<div class="timeline">' + segment(onboard, "Onboard assessment", "var(--cream)")
               + segment(trip, "Signal transit", "var(--muted)") + '</div>'
               + f'<small>{duration(onboard)} onboard + {duration(trip)} in transit</small>')
    markup('<div class="timeline">' + segment(delay, "Initial alert", "var(--muted)")
           + "".join(segment(2*delay, f"Exchange {i+1}", "var(--line)") for i in range(questions))
           + '</div>')
    st.caption("Simulation comparison. Radio estimate assumes immediate answers and one question per exchange. "
               "A flight surgeon could group questions. Both approaches use the same one-way signal delay.")


def case_screen(controller, ep, flow, packets, act, next_target, duration, guidance_view, exam_step, technical):
    eid = ep["episode_id"]
    title = SCENARIOS[ep["scenario_id"]]["title"]
    case_label = title.split(" · ")[0]
    stage = flow["display_stage"]
    ctx = controller.get_current_context(eid)
    suggested = flow.get("recording_ended_with_recheck", False)
    report = next((p for p in reversed(packets) if p["payload"].get("summary")), None)
    report_key = f"view_report:{eid}"
    compare_key = f"compare:{eid}"
    if report and st.session_state.get(compare_key):
        markup('<header class="topbar"><b>PATCH</b><small>Estimate from this simulation</small></header>')
        comparison(report, ep["clock"]["one_way_delay_seconds"], duration)
        if st.button("Back to handoff"):
            st.session_state[compare_key] = False
            st.rerun()
        if st.button(f"Start {case_label} again"):
            act(controller, "start", "start", scenario_id=ep["scenario_id"])
        return
    view_report = stage in ("REPORT", "SENT", "CLOSED") or (stage == "CRITICAL" and st.session_state.get(report_key))
    active = "Handoff" if view_report else {"SAFETY":"Safety","CRITICAL":"Safety","HISTORY":"Interview",
                                             "VITALS":"Vitals","EXAM":"Exam"}.get(stage, "Handoff")
    nav = "".join(f'<span class="{"on" if x == active else ""}">{x}</span>'
                  for x in ("Safety","Interview","Vitals","Exam","Handoff"))
    badge = '<b class="critical">Critical</b>' if stage == "CRITICAL" else ""
    markup(f'<header class="topbar"><b>PATCH</b><small>{escape(case_label)}</small><nav>{nav}</nav>{badge}'
           f'<time>{format_met(ep["clock"]["met_seconds"])}</time></header>')
    left, right = st.columns([2.25,1], gap="large")
    with left:
        if view_report:
            report_sheet(report["payload"]["summary"] if report else controller.build_handoff(eid), title)
            if not report and not ep["closed"] and st.button("Send handoff to Earth", type="primary"):
                st.session_state[compare_key] = True
                act(controller, "handoff", "handoff", episode_id=eid, replay_at=ep["clock"]["met_seconds"] + 55)
            if stage == "CRITICAL" and st.button("Return to critical pathway"):
                st.session_state[report_key] = False
                st.rerun()
            if report and st.button("Compare communication time", type="primary"):
                st.session_state[compare_key] = True
                st.rerun()
            if stage in ("REPORT", "SENT") and st.button("Request urgent review"):
                act(controller, "urgent_review", "urgent", episode_id=eid)
        elif stage in ("HISTORY","VITALS","EXAM"):
            dialogue = ctx["dialogue"]
            conversation(dialogue, playback=True)
            index = flow["step_index"]
            version = ep["state"]["state_version"]
            last = dialogue[-1]
            question_visible = (last["type"] == "patch_reply"
                                and last["payload"].get("question_index") == index
                                and last["payload"].get("state_version") == version)
            with st.container(horizontal=True, gap="small"):
                next_message = st.button("Next message", key="replay_next", type="primary")
                urgent_review = st.button("Request urgent review")
            if next_message:
                if question_visible:
                    act(controller, "recorded_step", f"answer:{eid}:{version}:{index}", episode_id=eid,
                        expected_step=index, expected_version=version, defer_question=True,
                        replay_at=70 + 60 * index + (20 if flow["current_step"].get("after_action") == "request_safety_recheck" else 0))
                else:
                    act(controller, "next_question", f"question:{eid}:{version}:{index}", episode_id=eid)
            if urgent_review:
                act(controller, "urgent_review", "urgent", episode_id=eid)
            st.caption("Click anywhere in the conversation or on the page background to advance.")
            st.html(Path(__file__).with_name("replay_click.html"), unsafe_allow_javascript=True)
            if ctx["observations"]:
                with st.expander("Recorded findings"):
                    for item in ctx["observations"]:
                        st.write(f"{item['metric']} · {item['value']} {item['unit']} · {item['source']}")
        else:
            if stage == "SAFETY":
                if suggested:
                    markup(bubble_html(ctx["dialogue"][-1]["payload"]["text"], crew=True, changed=True))
                safety(controller, ep, act, recheck=suggested or bool(ctx["checks"]), suggested=suggested)
            elif stage == "CRITICAL":
                with st.container(border=True, key="critical_card"):
                    st.caption("Simulated crew response · interview paused")
                    guidance_view(controller.get_safety_guidance(eid))
                if st.checkbox("Recheck responsiveness and breathing"):
                    safety(controller, ep, act, recheck=True, critical=True)
                if st.checkbox("Record findings after immediate actions"):
                    exam_step(controller, ep, flow)
                if st.button("Review clinical handoff", type="primary"):
                    st.session_state[report_key] = True
                    st.rerun()
                if report and st.button("Send updated critical handoff"):
                    st.session_state[report_key] = True
                    st.session_state[compare_key] = True
                    act(controller, "handoff", "critical_update", episode_id=eid)
            if any(e["type"] == "patch_reply" for e in ctx["dialogue"]):
                with st.expander("Recorded conversation"):
                    conversation(ctx["dialogue"], changed=suggested)
    with right:
        link_panel(ep, packets, act, controller, next_target, duration, technical)
    st.caption(f"{case_label} · recorded MedGemma interview · simulated patient and replay timing · not for clinical use")
