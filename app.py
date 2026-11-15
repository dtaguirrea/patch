"""PATCH Streamlit entry point. All mutations go through Controller.command."""
import json
import os
from pathlib import Path
from uuid import uuid4
import pandas as pd
import streamlit as st
from config_scenarios import SCENARIOS, load_scenario, exam_catalog, simulated_exam
from contracts import format_met
from controller import Controller
from space_link_db import SpaceLinkDB

st.set_page_config(page_title="PATCH · Mission care", page_icon="🛰️", layout="wide")
ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("PATCH_DB_PATH", str(ROOT / "data" / "patch_mvp.sqlite3")))


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
    st.session_state["notice"] = "Acción registrada."
    st.rerun()


def packet_table(packets):
    return [{"Tipo": p["kind"], "Estado": p["status"], "Creación": format_met(p["created_at_sim"]),
             "Envío": format_met(p["sent_at_sim"]), "Llegada prevista": format_met(p["arrives_at_sim"]),
             "Recepción": format_met(p["delivered_at_sim"]), "ID": p["packet_id"][:10]} for p in packets]


def show_observations(observations, now):
    if not observations:
        st.info("Todavía no hay resultados de exploración registrados.")
        return
    rows = []
    for o in observations:
        when = o["observed_at_sim"]
        rows.append({"Métrica": o["metric"], "Resultado": "—" if o["value"] is None else str(o["value"]),
            "Unidad": o["unit"], "Fuente": o["source"], "Calidad": o["quality"],
            "Observado": format_met(when), "Antigüedad (min)": None if when is None else round((now - when) / 60, 1),
            "Ingresado": format_met(o["entered_at_sim"]), "Procedencia": o["provenance"]})
    st.dataframe(rows, hide_index=True, use_container_width=True)


def spacecraft(controller, ep):
    eid = ep["episode_id"]
    now = ep["clock"]["met_seconds"]
    state = ep["state"]
    context = controller.get_current_context(eid)
    st.subheader("A bordo")
    cols = st.columns(4)
    cols[0].metric("Tiempo del episodio", format_met(now))
    cols[1].metric("Control HSM", state["hsm_state"])
    cols[2].metric("Enlace a Tierra", ep["clock"]["link_status"])
    cols[3].metric("Demora de ida", f'{ep["clock"]["one_way_delay_seconds"] / 60:g} min')
    if ep["closed"]:
        st.info("Episodio cerrado. El registro se conserva y los mensajes pendientes pueden completar su tránsito.")
    elif state["hsm_state"] == "CRITICAL":
        st.error(state["reason"] + " La entrevista está suspendida.")
    elif state["check_pending"]:
        st.warning(state["reason"])
    else:
        st.info(state["reason"])
    if ep["report_ready"]:
        st.caption("Informe generado. El monitoreo continúa mientras el episodio esté abierto.")

    left, right = st.columns([1, 1.6], gap="large")
    with left:
        st.markdown("#### Telemetría simulada")
        metrics = st.columns(2)
        for col, sample in zip(metrics, context["current_telemetry"]):
            col.metric("FC" if sample["metric"] == "pulse" else "SpO₂", f'{sample["value"]:g} {sample["unit"]}')
            col.caption(f'{format_met(sample["observed_at_sim"])} · {sample["source"]} · {sample["quality"]}')
        recent = controller.db.telemetry(eid, max(-3600, now - 3600), now)
        if recent:
            df = pd.DataFrame(recent)
            df["Minutos desde activación"] = df["observed_at_sim"] / 60
            chart = df.pivot_table(index="Minutos desde activación", columns="metric", values="value", aggfunc="last")
            st.line_chart(chart.rename(columns={"pulse": "FC (bpm)", "spo2": "SpO₂ (%)"}), height=180)
            st.caption("Escala compartida de demostración. Valores sintéticos, no señales de sensores reales.")
        with st.expander("Ficha previa · basales históricos"):
            st.json(ep["profile"])
            st.caption("Los basales no son mediciones actuales.")
        with st.expander("Caja negra inicial · T−60 min a T0"):
            st.caption("Copia persistente capturada al abrir el episodio y adjunta a INITIAL_ALERT.")
            st.dataframe(ep["initial_snapshot"], hide_index=True, use_container_width=True)
        if not ep["closed"] and state["hsm_state"] != "CRITICAL":
            st.markdown("#### Conciencia y respiración")
            st.caption("Resultados manuales del operador. Los guiones no incluyen respuestas iniciales aprobadas.")
            with st.form(f"check:{eid}:{state['state_version']}"):
                consciousness = st.selectbox("¿Está despierto y responde apropiadamente?", ["Sin seleccionar", "YES", "NO", "UNKNOWN"])
                breathing = st.selectbox("¿Respira normalmente sin dificultad aparente?", ["Sin seleccionar", "YES", "NO", "UNKNOWN"])
                if st.form_submit_button("Registrar chequeo", use_container_width=True):
                    act(controller, "check", "check", episode_id=eid, consciousness=consciousness, breathing=breathing)
            a, b = st.columns(2)
            if a.button("Recheck", use_container_width=True):
                act(controller, "recheck", "recheck", episode_id=eid)
            if b.button("Pedir revisión humana", use_container_width=True):
                act(controller, "urgent_review", "urgent", episode_id=eid)
            st.caption("Pedir revisión bloquea la entrevista y transmite una actualización; no significa que Tierra ya la haya recibido.")

    with right:
        st.markdown("#### Entrevista y registro")
        st.caption("MOCK · preguntas predefinidas · no interpreta lenguaje libre ni detecta emergencias relatadas solo por chat.")
        with st.container(height=390):
            for entry in context["dialogue"]:
                role = "assistant" if entry["type"] == "patch_reply" else "user"
                with st.chat_message(role):
                    st.write(entry["payload"]["text"])
                    label = "PATCH · mock" if role == "assistant" else "Tripulación"
                    st.caption(f'{label} · {format_met(entry["t_sim"])}')
                    if role == "assistant" and entry["payload"].get("state_version") != state["state_version"]:
                        st.caption("Turno histórico: no es una pregunta activa tras la revisión del estado.")
        if state["interview_enabled"] and not ep["closed"]:
            with st.form(f"chat:{eid}", clear_on_submit=True):
                message = st.text_area("Respuesta del astronauta", max_chars=8000, height=90)
                if st.form_submit_button("Enviar respuesta", type="primary"):
                    act(controller, "chat", "chat", episode_id=eid, text=message, expected_version=state["state_version"])
        elif state["hsm_state"] == "CRITICAL" and not ep["closed"]:
            st.warning("Valoración focalizada ilustrativa, pendiente de revisión clínica. Registre los hallazgos en Exploraciones.")
            st.markdown("**A ·** Capacidad para hablar y signos de vía aérea.\n\n**B ·** Trabajo respiratorio, FR y SpO₂ disponibles.\n\n**C ·** FC, PA obtenida y signos circulatorios disponibles.")
        else:
            st.caption("Complete el chequeo para habilitar el siguiente turno.")

    st.divider()
    st.markdown("#### Exploraciones y datos referidos")
    st.caption("Cada resultado conserva su fuente y hora. Los datos del guion solo se incorporan al registrarlos explícitamente.")
    catalog = context["exam_catalog"]
    if not ep["closed"]:
        with st.form(f"request:{eid}"):
            exam_id = st.selectbox("Solicitar exploración", list(catalog), format_func=lambda x: catalog[x]["label"])
            if st.form_submit_button("Crear solicitud"):
                act(controller, "request_exam", "request_exam", episode_id=eid, exam_id=exam_id)
        pending = controller.pending_exams(eid)
        if pending:
            request_ids = [r["event_id"] for r in pending]
            requests = {r["event_id"]: r for r in pending}
            request_id = st.selectbox("Solicitud a completar", request_ids,
                format_func=lambda x: f'{catalog[requests[x]["payload"]["exam_id"]]["label"]} · {format_met(requests[x]["t_sim"])}', key=f"pending:{eid}")
            metric = requests[request_id]["payload"]["exam_id"]
            scripted = simulated_exam(ep["scenario_id"], metric, now, deteriorated=ep["deteriorated"])
            st.info(f'Tarea del compañero: obtener/registrar {catalog[metric]["label"]} ({catalog[metric]["unit"]}).')
            if scripted is not None:
                st.caption(f"Resultado sintético disponible para esta solicitud: {scripted[0]} · procedencia {scripted[1]}. Aún no está registrado.")
                if st.button("Registrar resultado simulado del guion", key=f"script:{request_id}"):
                    act(controller, "record_exam", "script_exam", episode_id=eid, request_id=request_id, use_script=True)
            else:
                st.caption("No existe un resultado medido guionizado para esta fase. Ingrese el dato o registre su falta de disponibilidad.")
            with st.form(f"result:{request_id}"):
                value = st.text_input("Resultado", max_chars=1500)
                x, y, z = st.columns(3)
                source = x.selectbox("Fuente", ["exam_entry", "crew_reported"])
                quality = y.selectbox("Calidad / estado", ["valid", "unknown", "unavailable", "denied", "suspect"])
                timing = z.selectbox("Hora de observación", ["Ahora", "Minutos antes", "Desconocida"])
                minutes_ago = st.number_input("Minutos antes del reloj actual (si corresponde)", min_value=0, max_value=525600, value=0, step=1)
                candidates = [o for o in controller.db.observations(eid) if o["metric"] == metric]
                ids = [None] + [o["observation_id"] for o in candidates]
                labels = {o["observation_id"]: f'{o["value"]} · {format_met(o["observed_at_sim"])} · {o["observation_id"][:8]}' for o in candidates}
                replaces = st.selectbox("Corrección de un registro previo (opcional)", ids,
                    format_func=lambda x: "Nueva observación" if x is None else labels[x])
                if st.form_submit_button("Guardar resultado manual"):
                    observed = None if timing == "Desconocida" else now - (minutes_ago * 60 if timing == "Minutos antes" else 0)
                    act(controller, "record_exam", "manual_exam", episode_id=eid, request_id=request_id,
                        value=value, source=source, quality=quality, observed_at_sim=observed, replaces_observation_id=replaces)
    show_observations(context["observations"], now)
    if not ep["closed"]:
        st.markdown("#### Entrega a Tierra")
        st.caption("El informe utiliza una plantilla SBAR, datos registrados y transcripción. Generarlo no cierra la evaluación.")
        if st.button("Generar y enviar informe", type="primary"):
            act(controller, "handoff", "handoff", episode_id=eid)
    with st.expander("Cola de paquetes a bordo"):
        st.dataframe(packet_table(controller.db.packets(eid)), hide_index=True, use_container_width=True)
    with st.expander("Vista previa del informe actual · aún no enviado"):
        st.json(controller.build_handoff(eid))


def earth(controller, ep):
    st.subheader("Tierra · bandeja recibida")
    st.caption("Esta vista consulta exclusivamente paquetes entregados. Cada contenido es una instantánea del momento de creación; no refleja automáticamente cambios posteriores a bordo.")
    packets = controller.db.packets(ep["episode_id"], delivered_only=True)
    if not packets:
        st.info("No se han recibido paquetes de este episodio.")
        return
    st.dataframe(packet_table(packets), hide_index=True, use_container_width=True)
    for packet in reversed(packets):
        payload = packet["payload"]
        with st.expander(f'{packet["kind"]} · recibido {format_met(packet["delivered_at_sim"])} · creado {format_met(packet["created_at_sim"])}', expanded=True):
            st.write(f'Paciente: **{payload["patient_id"]}** · Estado comunicado: **{payload["state"]["hsm_state"]}**')
            st.write(payload["opening"])
            if payload["initial_check"] == "pending":
                st.warning("Chequeo pendiente al crear este paquete. No clasificar como estable.")
            st.caption(f'Versión de origen {packet["state_version"]} · envío {format_met(packet["sent_at_sim"])}')
            st.json(payload)
            st.download_button("Descargar paquete recibido", json.dumps(packet, ensure_ascii=False, indent=2),
                file_name=f'PATCH-{packet["packet_id"]}.json', mime="application/json", key=f'download:{packet["packet_id"]}')


def simulator(controller, ep):
    eid = ep["episode_id"]
    now = ep["clock"]["met_seconds"]
    st.subheader("Simulador · controles del operador")
    st.caption("El reloj es virtual: conversar o esperar frente a la pantalla no lo hace avanzar.")
    st.metric("Reloj del episodio", format_met(now))
    columns = st.columns(4)
    for col, minutes in zip(columns, [1, 5, 12, 15]):
        if col.button(f"+{minutes} min", use_container_width=True):
            act(controller, "advance", f"advance:{minutes}", episode_id=eid, target_time=now + minutes * 60)
    with st.form(f"clock:{eid}"):
        target_minutes = st.number_input("Ir al minuto absoluto desde T0", min_value=0, value=max(0, now // 60), step=1)
        if st.form_submit_button("Avanzar hasta ese instante"):
            act(controller, "advance", "target", episode_id=eid, target_time=target_minutes * 60)
    if ep["scenario_id"] == "N04":
        if st.button("Activar deterioro N04 · avanzar a T+00:02", disabled=ep["closed"] or ep["deteriorated"]):
            act(controller, "trigger_deterioration", "critical", episode_id=eid)
        st.caption("Evento determinista del simulador; no es detección por lenguaje ni umbral clínico universal.")
    if ep["scenario_id"] == "N06":
        cols = st.columns(5)
        for col, minute, label in zip(cols, [25, 360, 370, 420, 435], ["T+00:25", "T+06:00", "T+06:10", "T+07:00", "T+07:15"]):
            if col.button(label, disabled=now >= minute * 60, use_container_width=True):
                act(controller, "advance", f"jump:{minute}", episode_id=eid, target_time=minute * 60)
        st.caption("T+06:00 y T+07:00 significan seis y siete horas. Los informes de T+00:25 y T+06:10 se generan manualmente desde A bordo.")
    cols = st.columns(2)
    if cols[0].button("Cortar enlace", disabled=ep["clock"]["link_status"] == "DOWN"):
        act(controller, "set_link", "down", episode_id=eid, status="DOWN")
    if cols[1].button("Restablecer enlace", disabled=ep["clock"]["link_status"] == "UP"):
        act(controller, "set_link", "up", episode_id=eid, status="UP")
    st.caption("Los cambios manuales no eliminan el cronograma de N06. Los mensajes ya enviados continúan en tránsito durante un corte.")
    st.markdown("#### Transporte")
    st.dataframe(packet_table(controller.db.packets(eid)), hide_index=True, use_container_width=True)
    scenario = load_scenario(ep["scenario_id"])
    with st.expander("Guion privado del actor · nunca enviado al entrevistador ni a Tierra"):
        st.warning("Información para interpretar la simulación. No copiar hallazgos al diálogo antes de que se pregunte por ellos.")
        st.write(scenario["actor_notes"])
        st.write("Hipótesis oculta del guion:", scenario["hidden_truth"])
        st.write("Pendientes de revisión:")
        for item in scenario["pending"]:
            st.write("• " + item)
        st.json(scenario["schedule"])
    with st.expander("Contexto visible entregado al mock"):
        st.json(controller.get_current_context(eid))
    with st.expander("Registro de eventos"):
        st.json(controller.db.events(eid))
    trace = controller.export_trace(eid)
    st.download_button("Exportar traza completa JSON", json.dumps(trace, ensure_ascii=False, indent=2),
        file_name=f"PATCH-{eid}-trace.json", mime="application/json")
    if not ep["closed"]:
        with st.expander("Cerrar episodio con registro"):
            st.caption("El cierre conserva el estado HSM y envía una actualización final. No declara resolución clínica.")
            with st.form(f"close:{eid}"):
                note = st.text_area("Motivo / nota de cierre", max_chars=2000)
                if st.form_submit_button("Registrar cierre"):
                    act(controller, "close", "close", episode_id=eid, note=note)


def main():
    st.title("🛰️ PATCH")
    st.caption("Protocol-Assisted Triage, Communication & Handoff · simulación de misión a Marte")
    st.warning("Demostración con pacientes ficticios. No es software médico validado. Entrevistador MOCK; sin conexión real a MedGemma.")
    with SpaceLinkDB(DB_PATH) as db:
        controller = Controller(db)
        with st.sidebar:
            st.markdown("### Control de misión")
            scenario_id = st.selectbox("Escenario nuevo", list(SCENARIOS), format_func=lambda x: f'{x} · {SCENARIOS[x]["title"]}')
            scenario = load_scenario(scenario_id)
            with st.form(f"start:{scenario_id}"):
                opening = st.text_area("Motivo inicial", value=scenario["opening"], max_chars=8000)
                delay = st.number_input("Demora de ida (min)", min_value=0, max_value=1440, value=scenario["delay_seconds"] // 60)
                if st.form_submit_button("Iniciar episodio nuevo", type="primary", use_container_width=True):
                    act(controller, "start", "start", scenario_id=scenario_id, opening_text=opening, delay_seconds=delay * 60)
            st.caption("Iniciar crea un episodio independiente y conserva los anteriores. Use esta acción para reiniciar un escenario.")
            episodes = db.list_episodes()
            if not episodes:
                st.info("Seleccione un escenario e inicie el primer episodio.")
                return
            ids = [ep["episode_id"] for ep in episodes]
            if st.session_state.get("episode_selector") not in ids:
                persisted = db.get_setting("active_episode")
                st.session_state["episode_selector"] = persisted if persisted in ids else ids[0]
            eid = st.selectbox("Episodio abierto en pantalla", ids, key="episode_selector")
            if db.get_setting("active_episode") != eid:
                db.set_setting("active_episode", eid)
            st.caption("Los episodios, el reloj y los paquetes se recuperan al reiniciar la aplicación.")
        if st.session_state.pop("notice", None):
            st.toast("Acción registrada")
        ep = db.get_episode(eid)
        a, b, c = st.tabs(["A bordo", "Tierra", "Simulador"])
        with a:
            spacecraft(controller, ep)
        with b:
            earth(controller, ep)
        with c:
            simulator(controller, ep)


if __name__ == "__main__":
    main()
