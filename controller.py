"""Transactional application commands and chronological simulation scheduler."""
import hashlib
import json
from uuid import uuid4
from config_scenarios import load_scenario, exam_catalog, telemetry_at, simulated_exam
from contracts import (ClinicalEvent, ClinicalState, EpisodeSummary, MedicalMessage,
                       MissionClock, Observation, ProtocolState, TelemetrySample)
from core_hsm import evaluate_hsm, require_action
from llm_anamnesis import InterviewBackend
from space_link_db import SpaceLinkDB, encode


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
                    "trigger_deterioration": self.trigger_deterioration,
                    "request_exam": self.request_exam, "record_exam": self.record_exam,
                    "handoff": self.handoff, "set_link": self.set_link,
                    "close": self.close_episode}
        if action not in handlers:
            raise ValueError("Comando desconocido.")
        fingerprint = hashlib.sha256(json.dumps([action, kwargs], sort_keys=True).encode()).hexdigest()
        return self.db.execute_command(command_id, fingerprint, lambda: handlers[action](**kwargs))

    def _episode(self, episode_id, *, allow_closed=False):
        ep = self.db.get_episode(episode_id)
        if ep["closed"] and not allow_closed:
            raise ValueError("Episodio cerrado. Inicie uno nuevo para registrar otra evaluación.")
        return ep

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
            raise ValueError("Ingrese un motivo entre 1 y 8000 caracteres.")
        delay = scenario["delay_seconds"] if delay_seconds is None else delay_seconds
        if type(delay) is not int or not 0 <= delay <= 86400:
            raise ValueError("Demora inválida.")
        episode_id = f"{scenario_id}-{uid()[:12]}"
        ep = {"episode_id": episode_id, "scenario_id": scenario_id,
            "patient_id": scenario["public_profile"]["patient_id"], "profile": scenario["public_profile"],
            "clock": MissionClock(mission_id=episode_id, scenario_id=scenario_id,
                one_way_delay_seconds=delay).model_dump(mode="json"),
            "state": ProtocolState(episode_id=episode_id).model_dump(mode="json"),
            "initial_snapshot": [], "handled_schedule": [], "deteriorated": False,
            "closed": False, "report_ready": False, "opening": opening,
            "configuration_note": "Simulación. Valores [D] provisionales; chequeos manuales."
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
            "checks": [e for e in events if e["type"] == "initial_check"],
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
            "pending_exams": context["pending_exams"], "simulation": True}

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

    def check(self, episode_id, consciousness, breathing):
        ep = self._episode(episode_id)
        if consciousness not in ("YES", "NO", "UNKNOWN") or breathing not in ("YES", "NO", "UNKNOWN"):
            raise ValueError("Seleccione ambos resultados del chequeo.")
        event = self._event(ep, "initial_check", {"consciousness": consciousness, "breathing": breathing}, "crew")
        self._transition(ep, event)
        if ep["state"]["interview_enabled"]:
            return self.next_question(episode_id)
        return ep["state"]["reason"]

    def next_question(self, episode_id):
        ep = self._episode(episode_id)
        state = ProtocolState.model_validate(ep["state"])
        require_action(state, "interview")
        context = self.get_current_context(episode_id)
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
            raise ValueError("El entrevistador propuso una exploración fuera del catálogo.")
        self._event(current, "patch_reply", turn.model_dump(mode="json"), "mock")
        return turn.text

    def chat(self, episode_id, text, expected_version):
        ep = self._episode(episode_id)
        require_action(ProtocolState.model_validate(ep["state"]), "interview")
        if expected_version != ep["state"]["state_version"]:
            raise ValueError("La evaluación cambió. Actualice la vista antes de responder.")
        text = text.strip()
        if not text or len(text) > 8000:
            raise ValueError("El mensaje debe tener entre 1 y 8000 caracteres.")
        self._event(ep, "patient_message", {"text": text}, "crew")
        return self.next_question(episode_id)

    def recheck(self, episode_id, reason="Solicitud del compañero"):
        ep = self._episode(episode_id)
        event = self._event(ep, "recheck_requested", {"reason": reason,
            "telemetry": self.get_current_context(episode_id)["current_telemetry"]}, "crew")
        self._transition(ep, event)
        return ep["state"]

    def urgent_review(self, episode_id, reason="Solicitud manual de ayuda/revisión humana"):
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
            if item["type"] == "reassessment_event":
                obs = Observation(observation_id=uid(), episode_id=ep["episode_id"], patient_id=ep["patient_id"],
                    metric="temperature", value=39.1, unit="°C", observed_at_sim=now, entered_at_sim=now,
                    source="crew_reported", provenance="[G] declaración del guion N06")
                self.db.record_observation(obs)
                self._event(ep, "observation_recorded", obs.model_dump(mode="json"), "crew_reported")
            self.db.save_episode(ep)
            self._transition(ep, event)
        self.db.save_episode(ep)
        self._transport(ep)

    def advance_to(self, episode_id, target_time):
        ep = self._episode(episode_id, allow_closed=True)
        now = ep["clock"]["met_seconds"]
        if type(target_time) is not int or target_time < now:
            raise ValueError("El reloj solo puede avanzar.")
        if target_time - now > 172800:
            raise ValueError("Avance hasta 48 horas por operación.")
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

    def trigger_deterioration(self, episode_id):
        ep = self._episode(episode_id)
        if ep["scenario_id"] != "N04":
            raise ValueError("El deterioro guionizado solo está disponible para N04.")
        item = load_scenario("N04")["schedule"][0]
        if item["id"] in ep["handled_schedule"]:
            return "El deterioro ya se procesó."
        # Use the same clock path as scheduled deterioration, preserving T+2.
        return self.advance_to(episode_id, max(120, ep["clock"]["met_seconds"]))

    def set_link(self, episode_id, status):
        ep = self._episode(episode_id, allow_closed=True)
        if status not in ("UP", "DOWN"):
            raise ValueError("Estado de enlace inválido.")
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
        if exam_id not in exam_catalog(ep["scenario_id"]):
            raise ValueError("Exploración no disponible en el catálogo.")
        for pending in self.pending_exams(episode_id):
            if pending["payload"]["exam_id"] == exam_id:
                return pending["event_id"]
        return self._event(ep, "exam_requested", {"exam_id": exam_id}, "crew").event_id

    def record_exam(self, episode_id, request_id, value=None, source="exam_entry", quality="valid",
                    observed_at_sim=None, use_script=False, replaces_observation_id=None):
        ep = self._episode(episode_id)
        request = next((r for r in self.pending_exams(episode_id) if r["event_id"] == request_id), None)
        if request is None:
            raise ValueError("La solicitud no existe o ya se completó.")
        metric = request["payload"]["exam_id"]
        now = ep["clock"]["met_seconds"]
        provenance = "operator_entry"
        if source not in ("exam_entry", "crew_reported"):
            raise ValueError("Solo el simulador puede registrar sensores automáticos.")
        if use_script:
            result = simulated_exam(ep["scenario_id"], metric, now, deteriorated=ep["deteriorated"])
            if result is None:
                raise ValueError("No hay resultado medido en el guion para esta fase. Ingrese el resultado o registre UNAVAILABLE.")
            value, provenance = result
            source, quality, observed_at_sim = "exam_entry", "valid", now
        if quality in ("unknown", "unavailable"):
            value = None
        elif value is None or not str(value).strip():
            raise ValueError("Ingrese un resultado o marque UNKNOWN/UNAVAILABLE.")
        if replaces_observation_id:
            old = next((o for o in self.db.observations(episode_id) if o["observation_id"] == replaces_observation_id), None)
            if not old or old["metric"] != metric:
                raise ValueError("La corrección debe referenciar una observación de la misma métrica y episodio.")
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
        uncertainties = ["Simulación sin diagnóstico ni validación clínica.", "No hay inferencia LLM: síntesis por plantilla y transcripción literal."]
        if ep["state"]["check_pending"]:
            uncertainties.append("Chequeo de conciencia/respiración pendiente o desconocido.")
        if not context["observations"]:
            uncertainties.append("Sin exploraciones registradas.")
        if context["pending_exams"]:
            uncertainties.append("Hay exploraciones solicitadas sin resultado.")
        if any(o["observed_at_sim"] is None for o in context["observations"]):
            uncertainties.append("Existen observaciones de hora desconocida.")
        summary = EpisodeSummary(episode_id=episode_id, generated_at_sim=ep["clock"]["met_seconds"],
            sbar={"Situation": {"reason": ep["opening"], "control_state": ep["state"], "closed": ep["closed"]},
                  "Background": ep["profile"],
                  "Assessment": {"telemetry": context["current_telemetry"], "recorded_observations": context["observations"],
                      "interpretation": "Sin interpretación clínica automática; consultar transcripción y fuentes."},
                  "Recommendation": "Entrega documental para revisión humana; no constituye indicación terapéutica."},
            observations=context["observations"], transcript=context["dialogue"], checks=context["checks"],
            uncertainties=uncertainties, timeline=self.db.events(episode_id))
        return summary.model_dump(mode="json")

    def handoff(self, episode_id):
        ep = self._episode(episode_id)
        ep["report_ready"] = True
        self.db.save_episode(ep)
        return self._packet(ep, "CRITICAL_UPDATE" if ep["state"]["hsm_state"] == "CRITICAL" else "CLINICAL_UPDATE", self.build_handoff(episode_id))

    def close_episode(self, episode_id, note):
        ep = self._episode(episode_id)
        if not note.strip():
            raise ValueError("Documente el motivo de cierre.")
        ep["closed"] = True
        ep["state"]["interview_enabled"] = False
        ep["state"]["state_version"] += 1
        ep["state"]["updated_at_sim"] = ep["clock"]["met_seconds"]
        event = self._event(ep, "episode_closed", {"note": note.strip()}, "operator")
        ep["state"]["trigger_event_id"] = event.event_id
        ep["state"]["reason"] = "Episodio cerrado por el operador."
        self.db.save_episode(ep)
        self._packet(ep, "CLINICAL_UPDATE", self.build_handoff(episode_id))
        return episode_id

    def export_trace(self, episode_id):
        ep = self.db.get_episode(episode_id)
        return {"format": "PATCH-MVP-1", "simulation": True, "episode": ep,
                "events": self.db.events(episode_id), "observations": self.db.observations(episode_id),
                "telemetry": self.db.telemetry(episode_id, -3600, ep["clock"]["met_seconds"]),
                "packets": self.db.packets(episode_id)}
