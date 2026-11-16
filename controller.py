"""Transactional application commands and chronological simulation scheduler."""
import hashlib
import json
from uuid import uuid4
from config_scenarios import load_scenario, load_recorded_case, exam_catalog, telemetry_at, simulated_exam
from contracts import (ClinicalEvent, ClinicalState, EpisodeSummary, MedicalMessage,
                       MissionClock, Observation, ProtocolState, TelemetrySample)
from core_hsm import evaluate_hsm, require_action
from llm_anamnesis import InterviewBackend, QUESTIONS, RECHECK_QUESTIONS
from space_link_db import SpaceLinkDB, encode
from emergency_guidance import QUESTION_SET, guidance_for_answers


def uid():
    return uuid4().hex


class Controller:
    def __init__(self, db: SpaceLinkDB):
        self.db = db
        self.backend = InterviewBackend()

    def command(self, action: str, *, command_id: str, **kwargs):
        handlers = {"start": self.start_episode, "check": self.check, "chat": self.chat,
                    "next_question": self.next_question, "advance": self.advance_to,
                    "recheck": self.recheck, "urgent_review": self.urgent_review,
                    "request_exam": self.request_exam, "record_exam": self.record_exam,
                    "handoff": self.handoff, "set_link": self.set_link,
                    "close": self.close_episode, "recorded_step": self.recorded_step,
                    "complete_phase": self.complete_phase, "critical_check": self.critical_check}
        if action not in handlers:
            raise ValueError("Unknown command.")
        fingerprint = hashlib.sha256(json.dumps([action, kwargs], sort_keys=True).encode()).hexdigest()
        def execute():
            # Optional pacing for the Case 4 replay, atomic with the action it dates.
            replay_time = kwargs.pop("replay_at", None)
            if replay_time is not None:
                ep = self._episode(kwargs["episode_id"])
                if ep["scenario_id"] != "C04" or action not in {"check", "recorded_step", "handoff"}:
                    raise ValueError("Replay timing is only available for the Case 4 walkthrough.")
                self.advance_to(ep["episode_id"], max(ep["clock"]["met_seconds"], replay_time))
            return handlers[action](**kwargs)

        return self.db.execute_command(command_id, fingerprint, execute)

    def _episode(self, episode_id, *, allow_closed=False):
        ep = self.db.get_episode(episode_id)
        if ep["closed"] and not allow_closed:
            raise ValueError("Episode closed. Start a new one to record another assessment.")
        return ep

    def _workflow(self, ep):
        """Persist new flows; derive a conservative resume point for old episodes."""
        if "workflow" not in ep:
            count = sum(e["type"] == "patient_message" for e in self.db.events(ep["episode_id"]))
            ep["workflow"] = {"stage": "SENT" if ep["report_ready"] else "HISTORY",
                              "step_index": min(count, 5), "observation_start": 0}
        return ep["workflow"]

    def get_workflow(self, episode_id):
        ep = self.db.get_episode(episode_id)
        workflow = dict(self._workflow(ep))
        workflow["recorded"] = load_scenario(ep["scenario_id"]).get("recorded_case", False)
        if ep["closed"]:
            workflow["display_stage"] = "CLOSED"
        elif ep["state"]["hsm_state"] == "CRITICAL":
            workflow["display_stage"] = "CRITICAL"
        elif ep["state"]["check_pending"]:
            workflow["display_stage"] = "SAFETY"
        else:
            workflow["display_stage"] = workflow["stage"]
        if workflow["recorded"]:
            case = load_recorded_case(ep["scenario_id"])
            workflow["total_steps"] = len(case["steps"])
            # This is an operator-facing view, not LLM or Earth context.
            if workflow["display_stage"] in ("HISTORY", "VITALS", "EXAM"):
                workflow["current_step"] = case["steps"][workflow["step_index"]]
        return workflow

    def _require_flow(self, ep, allowed):
        self._require_safety_clearance(ep)
        if ep["state"]["check_pending"] or not ep["state"]["interview_enabled"]:
            raise ValueError("Complete both responsiveness and breathing checks first.")
        if self._workflow(ep)["stage"] not in allowed:
            raise ValueError("This action is not available in the current stage.")

    def _require_safety_clearance(self, ep):
        checks = [e for e in self.db.events(ep["episode_id"])
                  if e["type"] in ("initial_check", "critical_recheck")]
        if (not checks or any(checks[-1]["payload"].get(field) != "YES"
                              for field in ("consciousness", "breathing"))
                or ep["state"]["check_pending"] or not ep["state"]["interview_enabled"]):
            raise ValueError("Both safety questions must be answered YES and saved before the interview can start.")

    def get_safety_guidance(self, episode_id):
        ep = self.db.get_episode(episode_id)
        events = self.db.events(episode_id)
        checks = [(i, e) for i, e in enumerate(events) if e["type"] in ("initial_check", "critical_recheck")]
        critical = ep["state"]["hsm_state"] == "CRITICAL"
        if checks:
            index, check = checks[-1]
            stale = any(e["type"] in ("critical_event", "recheck_requested", "reassessment_event", "human_review_requested")
                        for e in events[index + 1:])
            # Earlier versions asked about responding appropriately, which does
            # not establish unresponsiveness. Never infer cardiac arrest from it.
            if not stale and check["payload"].get("question_set") == QUESTION_SET:
                result = guidance_for_answers(check["payload"]["consciousness"],
                                              check["payload"]["breathing"], critical=critical)
                return result | {"based_on_event_id": check["event_id"], "checked_at_sim": check["t_sim"]}
        return guidance_for_answers(critical=critical) | {"based_on_event_id": None, "checked_at_sim": None}

    def critical_check(self, episode_id, consciousness, breathing):
        ep = self._episode(episode_id)
        if ep["state"]["hsm_state"] != "CRITICAL":
            raise ValueError("Emergency reassessment is available only in the critical pathway.")
        if consciousness not in ("YES", "NO", "UNKNOWN") or breathing not in ("YES", "NO", "UNKNOWN"):
            raise ValueError("Select an answer to both safety questions.")
        event = self._event(ep, "critical_recheck", {"consciousness": consciousness, "breathing": breathing,
            "question_set": QUESTION_SET}, "crew")
        ep["state"].update(state_version=ep["state"]["state_version"] + 1,
            updated_at_sim=ep["clock"]["met_seconds"], trigger_event_id=event.event_id,
            interview_enabled=False, check_pending=False,
            reason="Emergency checks updated. Critical review remains active; the interview stays blocked.")
        self.db.save_episode(ep)
        self._packet(ep, "CRITICAL_UPDATE")
        return self.get_safety_guidance(episode_id)

    def _set_phase(self, ep, stage):
        workflow = self._workflow(ep)
        before = workflow["stage"]
        workflow["stage"] = stage
        self.db.save_episode(ep)
        if before != stage:
            self._event(ep, "workflow_phase_changed", {"before": before, "after": stage})

    def phase_exam_ids(self, episode_id):
        ep = self.db.get_episode(episode_id)
        stage = self.get_workflow(episode_id)["display_stage"]
        if stage == "CRITICAL":
            return list(exam_catalog(ep["scenario_id"]))
        if load_scenario(ep["scenario_id"]).get("recorded_case"):
            return []
        catalog = exam_catalog(ep["scenario_id"])
        if stage == "VITALS":
            return [key for key in ("blood_pressure", "respiratory_rate", "temperature") if key in catalog]
        if stage == "EXAM":
            return [key for key in ("abdomen", "skin", "capillary_refill") if key in catalog]
        if stage == "CRITICAL":
            return list(catalog)
        return []

    def phase_remaining_exams(self, episode_id):
        ep = self.db.get_episode(episode_id)
        start = self._workflow(ep)["observation_start"]
        completed = {o["metric"] for o in self.db.observations(episode_id)[start:]}
        return [key for key in self.phase_exam_ids(episode_id) if key not in completed]

    def complete_phase(self, episode_id, expected_stage):
        ep = self._episode(episode_id)
        if load_scenario(ep["scenario_id"]).get("recorded_case"):
            raise ValueError("Read and record the current turn of the recorded case.")
        self._require_flow(ep, {"VITALS", "EXAM"})
        if expected_stage != self._workflow(ep)["stage"]:
            raise ValueError("The stage has changed. Refresh the page.")
        if self.phase_remaining_exams(episode_id):
            raise ValueError("Record each result or explicitly mark it unknown/unavailable.")
        self._set_phase(ep, "EXAM" if expected_stage == "VITALS" else "REPORT")
        return self._workflow(ep)["stage"]

    def recorded_step(self, episode_id, expected_step, expected_version, defer_question=False):
        ep = self._episode(episode_id)
        self._require_flow(ep, {"HISTORY", "VITALS", "EXAM"})
        case = load_recorded_case(ep["scenario_id"])
        workflow = self._workflow(ep)
        if expected_step != workflow["step_index"] or expected_version != ep["state"]["state_version"]:
            raise ValueError("The turn or safety check has changed. Refresh before continuing.")
        step = case["steps"][expected_step]
        event = self._event(ep, "patient_message", {"text": step["answer"], "recorded": True,
            "case_step": expected_step, "source_file": case["source_file"],
            "source_dialogue_index": step["source_dialogue_index"]}, "crew")
        for value in step["observations"]:
            observation = Observation(observation_id=uid(), episode_id=episode_id,
                patient_id=ep["patient_id"], **value, observed_at_sim=None,
                entered_at_sim=ep["clock"]["met_seconds"], source="crew_reported",
                provenance=f"{case['source_file']} · dialogue[{step['source_dialogue_index']}] · event {event.event_id}")
            self.db.record_observation(observation)
            self._event(ep, "observation_recorded", observation.model_dump(mode="json"), "crew_reported")
        workflow["step_index"] += 1
        next_stage = case["steps"][workflow["step_index"]]["phase"] if workflow["step_index"] < len(case["steps"]) else "REPORT"
        self._set_phase(ep, next_stage)
        if step.get("after_action") == "request_safety_recheck":
            # This curated fixture requests a recheck; recorded model text never
            # determines CRITICAL. Only the explicit safety answers do that.
            workflow["recording_ended_with_recheck"] = True
            self.db.save_episode(ep)
            suggestion = self._event(ep, "recheck_requested", {
                "reason": "The recorded crewmate reports a change in condition.",
                "crew_statement": step["answer"],
                "source_file": case["source_file"],
                "terminal_source": case["terminal_source"],
            }, "recorded_replay")
            self._transition(ep, suggestion)
            self._packet(ep, "CLINICAL_UPDATE")
            return "SAFETY"
        if next_stage != "REPORT" and not defer_question:
            self.next_question(episode_id)
        return next_stage

    def _event(self, ep, event_type, payload=None, source="controller"):
        event = ClinicalEvent(event_id=uid(), episode_id=ep["episode_id"], type=event_type,
            source=source, t_sim=ep["clock"]["met_seconds"], payload=payload or {})
        self.db.record_event(event)
        return event

    def _transport(self, ep):
        self.db.process_transport(ep["episode_id"], ep["clock"]["met_seconds"],
            ep["clock"]["link_status"] == "UP", ep["clock"]["one_way_delay_seconds"])

    def _transition(self, ep, event):
        before = ProtocolState.model_validate(ep["state"])
        after = evaluate_hsm(before, event)
        if after != before:
            ep["state"] = after.model_dump(mode="json")
            if event.type in ("recheck_requested", "reassessment_event", "human_review_requested") and after.hsm_state != ClinicalState.CRITICAL:
                ep["report_ready"] = False
                if not load_scenario(ep["scenario_id"]).get("recorded_case"):
                    ep["workflow"] = {"stage": "HISTORY", "step_index": 0,
                        "observation_start": len(self.db.observations(ep["episode_id"])),
                        "reassessment": True, "history_limit": len(RECHECK_QUESTIONS)}
                elif self._workflow(ep)["stage"] == "SENT":
                    ep["workflow"]["stage"] = "REPORT"
            self.db.save_episode(ep)
            self._event(ep, "state_changed", {"before": before.model_dump(mode="json"), "after": ep["state"]})
        if after.hsm_state == ClinicalState.CRITICAL and before.hsm_state != ClinicalState.CRITICAL:
            self._packet(ep, "CRITICAL_UPDATE")

    def _sensors(self, ep, now, force=False):
        if ep.get("last_sample") == now and not force:
            return
        values = telemetry_at(ep["scenario_id"], now, deteriorated=ep.get("deteriorated", False))
        for metric, value in values.items():
            sample = TelemetrySample(sample_id=uid(), episode_id=ep["episode_id"], patient_id=ep["patient_id"],
                metric=metric, value=value, unit="bpm" if metric == "pulse" else "%", observed_at_sim=now)
            self.db.record_telemetry(sample)
        ep["last_sample"] = now

    def start_episode(self, scenario_id: str, opening_text: str | None = None, delay_seconds: int | None = None):
        scenario = load_scenario(scenario_id)
        opening = (scenario["opening"] if opening_text is None else opening_text).strip()
        if not opening or len(opening) > 8000:
            raise ValueError("Enter a presenting concern between 1 and 8000 characters.")
        delay = scenario["delay_seconds"] if delay_seconds is None else delay_seconds
        if type(delay) is not int or not 0 <= delay <= 86400:
            raise ValueError("Invalid delay.")
        episode_id = f"{scenario_id}-{uid()[:12]}"
        ep = {"episode_id": episode_id, "scenario_id": scenario_id,
            "patient_id": scenario["public_profile"]["patient_id"], "profile": scenario["public_profile"],
            "clock": MissionClock(mission_id=episode_id, scenario_id=scenario_id,
                one_way_delay_seconds=delay).model_dump(mode="json"),
            "state": ProtocolState(episode_id=episode_id).model_dump(mode="json"),
            "initial_snapshot": [], "handled_schedule": [], "deteriorated": False,
            "closed": False, "report_ready": False, "opening": opening,
            "workflow": {"stage": "HISTORY", "step_index": 0, "observation_start": 0},
            "configuration_note": "Recorded demo case. No live inference or sensor feed; manual safety checks."
        }
        self.db.insert_episode(ep)
        for now in range(-3600, 1, 60):
            self._sensors(ep, now)
        ep["initial_snapshot"] = self.db.telemetry(episode_id, -3600, 0)
        self.db.save_episode(ep)
        self._event(ep, "episode_started", {"scenario_id": scenario_id})
        self._event(ep, "opening_message", {"text": opening}, "crew")
        self._packet(ep, "INITIAL_ALERT")
        return episode_id

    def get_current_context(self, episode_id: str):
        """Explicit allowlist: no private fixtures, future events or scripted results."""
        ep = self.db.get_episode(episode_id)
        now = ep["clock"]["met_seconds"]
        latest = {}
        for sample in self.db.telemetry(episode_id, max(-3600, now - 3600), now):
            latest[sample["metric"]] = sample
        events = self.db.events(episode_id)
        observations = self.db.observations(episode_id)
        replaced = {o["replaces_observation_id"] for o in observations if o["replaces_observation_id"]}
        current_observations = [o | {"age_seconds": None if o["observed_at_sim"] is None else now - o["observed_at_sim"]}
                                for o in observations if o["observation_id"] not in replaced]
        return {"episode_id": episode_id, "patient_id": ep["patient_id"], "profile": ep["profile"],
            "mission": ep["clock"], "state_version": ep["state"]["state_version"], "state": ep["state"],
            "current_telemetry": list(latest.values()), "observations": current_observations,
            "checks": [e for e in events if e["type"] in ("initial_check", "critical_recheck")],
            "dialogue": [e for e in events if e["type"] in ("opening_message", "patient_message", "patch_reply", "crew_statement")],
            "exam_catalog": exam_catalog(ep["scenario_id"]),
            "pending_exams": self.pending_exams(episode_id)}

    def _snapshot(self, ep):
        context = self.get_current_context(ep["episode_id"])
        return {"episode_id": ep["episode_id"], "patient_id": ep["patient_id"],
            "scenario_id": ep["scenario_id"], "captured_at_sim": ep["clock"]["met_seconds"],
            "profile": context["profile"], "opening": ep["opening"], "state": context["state"],
            "initial_check": context["checks"][-1] if context["checks"] else "pending",
            "current_telemetry": context["current_telemetry"], "observations": context["observations"],
            "checks": context["checks"], "transcript": context["dialogue"],
            "pending_exams": context["pending_exams"], "simulation": True,
            "safety_guidance": self.get_safety_guidance(ep["episode_id"])}

    def _packet(self, ep, kind, summary=None):
        payload = self._snapshot(ep)
        if kind == "INITIAL_ALERT":
            payload["black_box_snapshot"] = ep["initial_snapshot"]
        if summary is not None:
            payload["summary"] = summary
        packet = MedicalMessage(packet_id=uid(), episode_id=ep["episode_id"], kind=kind,
            created_at_sim=ep["clock"]["met_seconds"], state_version=ep["state"]["state_version"], payload=payload)
        self.db.create_packet(packet)
        self._event(ep, "packet_created", {"packet_id": packet.packet_id, "kind": kind})
        self._transport(ep)
        return packet.packet_id

    def check(self, episode_id, consciousness, breathing, defer_question=False):
        ep = self._episode(episode_id)
        if not ep["state"]["check_pending"]:
            raise ValueError("The safety check has already been recorded. Request a recheck to repeat it.")
        if consciousness not in ("YES", "NO", "UNKNOWN") or breathing not in ("YES", "NO", "UNKNOWN"):
            raise ValueError("Select an answer to both safety questions.")
        event = self._event(ep, "initial_check", {"consciousness": consciousness, "breathing": breathing,
            "question_set": QUESTION_SET}, "crew")
        self._transition(ep, event)
        if ep["state"]["interview_enabled"] and not defer_question:
            return self.next_question(episode_id)
        return ep["state"]["reason"]

    def next_question(self, episode_id):
        ep = self._episode(episode_id)
        state = ProtocolState.model_validate(ep["state"])
        require_action(state, "interview")
        self._require_safety_clearance(ep)
        workflow = self._workflow(ep)
        recorded = load_scenario(ep["scenario_id"]).get("recorded_case")
        if workflow["stage"] not in ({"HISTORY", "VITALS", "EXAM"} if recorded else {"HISTORY"}):
            return None
        context = self.get_current_context(episode_id)
        if recorded:
            step = load_recorded_case(ep["scenario_id"])["steps"][workflow["step_index"]]
            context["instruction"] = {"text": step["question"], "index": workflow["step_index"],
                                      "recorded": True}
        else:
            questions = RECHECK_QUESTIONS if workflow.get("reassessment") else QUESTIONS[:5]
            context["instruction"] = {"text": questions[min(workflow["step_index"], len(questions) - 1)],
                                      "index": workflow["step_index"], "recorded": False}
        # Do not duplicate an unanswered question on a rerender/retry.
        if context["dialogue"] and context["dialogue"][-1]["type"] == "patch_reply":
            last = context["dialogue"][-1]["payload"]
            if last.get("state_version") == state.state_version:
                return last["text"]
        turn = self.backend.generate(context)
        current = self.db.get_episode(episode_id)
        if (current["closed"] or current["state"]["state_version"] != turn.state_version
                or not current["state"]["interview_enabled"] or turn.episode_id != episode_id):
            self._event(current, "discarded_stale_llm_output", {"turn_id": turn.turn_id})
            return None
        if any(item not in context["exam_catalog"] for item in turn.exam_plan):
            raise ValueError("The interviewer proposed an examination outside the catalog.")
        self._event(current, "patch_reply", turn.model_dump(mode="json"), "recorded_replay" if recorded else "mock")
        return turn.text

    def chat(self, episode_id, text, expected_version):
        ep = self._episode(episode_id)
        require_action(ProtocolState.model_validate(ep["state"]), "interview")
        self._require_flow(ep, {"HISTORY"})
        if load_scenario(ep["scenario_id"]).get("recorded_case"):
            raise ValueError("This case uses recorded answers; record the scripted turn.")
        if expected_version != ep["state"]["state_version"]:
            raise ValueError("The assessment has changed. Refresh before responding.")
        text = text.strip()
        if not text or len(text) > 8000:
            raise ValueError("The message must contain between 1 and 8000 characters.")
        self._event(ep, "patient_message", {"text": text}, "crew")
        workflow = self._workflow(ep)
        workflow["step_index"] += 1
        self._set_phase(ep, "VITALS" if workflow["step_index"] >= workflow.get("history_limit", 5) else "HISTORY")
        return self.next_question(episode_id)

    def recheck(self, episode_id, reason="Crewmate request"):
        ep = self._episode(episode_id)
        event = self._event(ep, "recheck_requested", {"reason": reason,
            "telemetry": self.get_current_context(episode_id)["current_telemetry"]}, "crew")
        self._transition(ep, event)
        return ep["state"]

    def urgent_review(self, episode_id, reason="Manual request for help / human review"):
        ep = self._episode(episode_id)
        event = self._event(ep, "human_review_requested", {"reason": reason}, "crew")
        self._transition(ep, event)
        self._packet(ep, "CRITICAL_UPDATE" if ep["state"]["hsm_state"] == "CRITICAL" else "CLINICAL_UPDATE")
        return ep["state"]

    def _scheduled(self, ep, item):
        if item["id"] in ep["handled_schedule"]:
            return
        ep["handled_schedule"].append(item["id"])
        event = self._event(ep, item["type"], item["payload"] | {"schedule_id": item["id"]}, "simulator")
        now = ep["clock"]["met_seconds"]
        if item["type"] == "link_change":
            ep["clock"]["link_status"] = item["payload"]["status"]
        else:
            if item["type"] == "critical_event":
                ep["deteriorated"] = True
            self._sensors(ep, now, force=True)
            if "crew_statement" in item["payload"]:
                self._event(ep, "crew_statement", {"text": item["payload"]["crew_statement"]}, "crew")
            self.db.save_episode(ep)
            self._transition(ep, event)
        self.db.save_episode(ep)
        self._transport(ep)

    def advance_to(self, episode_id, target_time):
        ep = self._episode(episode_id, allow_closed=True)
        now = ep["clock"]["met_seconds"]
        if type(target_time) is not int or target_time < now:
            raise ValueError("The clock can only move forward.")
        if target_time - now > 172800:
            raise ValueError("Advance by at most 48 hours per operation.")
        schedule = load_scenario(ep["scenario_id"])["schedule"]
        while now < target_time:
            times = [target_time, ((now // 60) + 1) * 60]
            if not ep["closed"]:
                times += [e["at"] for e in schedule if e["id"] not in ep["handled_schedule"] and now < e["at"] <= target_time]
            times += [p["arrives_at_sim"] for p in self.db.packets(episode_id)
                      if p["status"] == "IN_TRANSIT" and now < p["arrives_at_sim"] <= target_time]
            now = min(times)
            ep["clock"]["met_seconds"] = now
            ep["clock"]["version"] += 1
            self.db.save_episode(ep)
            for item in sorted(schedule, key=lambda x: (x["at"], x["id"])):
                if not ep["closed"] and item["at"] == now and item["id"] not in ep["handled_schedule"]:
                    self._scheduled(ep, item)
            if now % 60 == 0 and not ep["closed"]:
                self._sensors(ep, now)
            self.db.save_episode(ep)
            self._transport(ep)
        self._transport(ep)
        return ep["clock"]

    def set_link(self, episode_id, status):
        ep = self._episode(episode_id, allow_closed=True)
        if status not in ("UP", "DOWN"):
            raise ValueError("Invalid link status.")
        ep["clock"]["link_status"] = status
        ep["clock"]["version"] += 1
        self._event(ep, "link_change", {"status": status, "manual": True}, "operator")
        self.db.save_episode(ep)
        self._transport(ep)
        return status

    def pending_exams(self, episode_id):
        events = self.db.events(episode_id)
        completed = {e["payload"].get("request_id") for e in events if e["type"] == "exam_completed"}
        return [e for e in events if e["type"] == "exam_requested" and e["event_id"] not in completed]

    def request_exam(self, episode_id, exam_id):
        ep = self._episode(episode_id)
        if exam_id not in self.phase_exam_ids(episode_id):
            raise ValueError("This examination is not enabled in the current workflow stage.")
        if exam_id not in exam_catalog(ep["scenario_id"]):
            raise ValueError("Examination not available in the catalog.")
        for pending in self.pending_exams(episode_id):
            if pending["payload"]["exam_id"] == exam_id:
                return pending["event_id"]
        return self._event(ep, "exam_requested", {"exam_id": exam_id}, "crew").event_id

    def record_exam(self, episode_id, request_id, value=None, source="exam_entry", quality="valid",
                    observed_at_sim=None, use_script=False, replaces_observation_id=None):
        ep = self._episode(episode_id)
        request = next((r for r in self.pending_exams(episode_id) if r["event_id"] == request_id), None)
        if request is None:
            raise ValueError("The request does not exist or has already been completed.")
        metric = request["payload"]["exam_id"]
        if metric not in self.phase_exam_ids(episode_id):
            raise ValueError("The request belongs to a stage that is not currently enabled.")
        now = ep["clock"]["met_seconds"]
        provenance = "operator_entry"
        if source not in ("exam_entry", "crew_reported"):
            raise ValueError("Only the simulator can record automatic sensor readings.")
        if use_script:
            result = simulated_exam(ep["scenario_id"], metric, now, deteriorated=ep["deteriorated"])
            if result is None:
                raise ValueError("No scripted measured result exists for this phase. Enter a result or record UNAVAILABLE.")
            value, provenance = result
            source, quality, observed_at_sim = "exam_entry", "valid", now
        if quality in ("unknown", "unavailable"):
            value = None
        elif value is None or not str(value).strip():
            raise ValueError("Enter a result or mark UNKNOWN/UNAVAILABLE.")
        if replaces_observation_id:
            old = next((o for o in self.db.observations(episode_id) if o["observation_id"] == replaces_observation_id), None)
            if not old or old["metric"] != metric:
                raise ValueError("A correction must reference an observation of the same metric and episode.")
        observation = Observation(observation_id=uid(), episode_id=episode_id, patient_id=ep["patient_id"],
            metric=metric, value=value, unit=exam_catalog(ep["scenario_id"])[metric]["unit"],
            source=source, quality=quality, observed_at_sim=observed_at_sim, entered_at_sim=now,
            provenance=provenance, replaces_observation_id=replaces_observation_id)
        self.db.record_observation(observation)
        self._event(ep, "observation_recorded", observation.model_dump(mode="json"), source)
        self._event(ep, "exam_completed", {"request_id": request_id, "observation_id": observation.observation_id})
        return observation.observation_id

    def build_handoff(self, episode_id):
        ep = self.db.get_episode(episode_id)
        context = self.get_current_context(episode_id)
        uncertainties = ["Simulation without diagnosis or clinical validation.", "No live LLM inference: template summary and verbatim transcript."]
        if ep["state"]["check_pending"]:
            uncertainties.append("Responsiveness/breathing check is pending or unknown.")
        if not context["observations"]:
            uncertainties.append("No examinations recorded.")
        if context["pending_exams"]:
            uncertainties.append("Some requested examinations have no result.")
        if any(o["observed_at_sim"] is None for o in context["observations"]):
            uncertainties.append("Some observations have unknown observation times.")
        if load_scenario(ep["scenario_id"]).get("recorded_case"):
            uncertainties.extend(load_recorded_case(ep["scenario_id"])["notes"])
            observed_metrics = {o["metric"] for o in context["observations"]}
            uncertainties.extend(f"No supplied result: {metric}." for metric in
                ("blood_pressure", "temperature", "respiratory_rate") if metric not in observed_metrics)
        summary = EpisodeSummary(episode_id=episode_id, generated_at_sim=ep["clock"]["met_seconds"],
            sbar={"Situation": {"reason": ep["opening"], "control_state": ep["state"], "closed": ep["closed"]},
                  "Background": ep["profile"],
                  "Assessment": {"telemetry": context["current_telemetry"], "recorded_observations": context["observations"],
                      "interpretation": "No automatic clinical interpretation; consult the transcript and sources."},
                  "Recommendation": "Documented handoff for human review; not a treatment order."},
            observations=context["observations"], transcript=context["dialogue"], checks=context["checks"],
            uncertainties=uncertainties, timeline=self.db.events(episode_id))
        return summary.model_dump(mode="json")

    def handoff(self, episode_id):
        ep = self._episode(episode_id)
        if ep["state"]["hsm_state"] != "CRITICAL":
            self._require_flow(ep, {"REPORT"})
        ep["report_ready"] = True
        if load_scenario(ep["scenario_id"]).get("recorded_case") and ep["state"]["hsm_state"] != "CRITICAL":
            ep["state"]["reason"] = "Recorded workflow complete; handoff available."
        self._set_phase(ep, "SENT")
        self.db.save_episode(ep)
        return self._packet(ep, "CRITICAL_UPDATE" if ep["state"]["hsm_state"] == "CRITICAL" else "CLINICAL_UPDATE", self.build_handoff(episode_id))

    def close_episode(self, episode_id, note):
        ep = self._episode(episode_id)
        if not ep["report_ready"]:
            raise ValueError("Generate a handoff before closing the episode.")
        if not note.strip():
            raise ValueError("Document the reason for closure.")
        ep["closed"] = True
        ep["state"]["interview_enabled"] = False
        ep["state"]["state_version"] += 1
        ep["state"]["updated_at_sim"] = ep["clock"]["met_seconds"]
        event = self._event(ep, "episode_closed", {"note": note.strip()}, "operator")
        ep["state"]["trigger_event_id"] = event.event_id
        ep["state"]["reason"] = "Episode closed by the operator."
        self.db.save_episode(ep)
        self._packet(ep, "CLINICAL_UPDATE", self.build_handoff(episode_id))
        return episode_id

    def export_trace(self, episode_id):
        ep = self.db.get_episode(episode_id)
        return {"format": "PATCH-MVP-1", "simulation": True, "episode": ep,
                "events": self.db.events(episode_id), "observations": self.db.observations(episode_id),
                "telemetry": self.db.telemetry(episode_id, -3600, ep["clock"]["met_seconds"]),
                "packets": self.db.packets(episode_id)}
