"""SQLite storage and the delayed spacecraft–Earth link for PATCH."""

import sqlite3
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import TypeVar

from pydantic import JsonValue, TypeAdapter

from contracts import (
    AckPayload,
    ClinicalAssessmentTurn,
    ClinicalEvent,
    ClinicalFinding,
    Contract,
    LinkStatus,
    MedicalMessage,
    MessageDirection,
    MessageKind,
    MessageStatus,
    METSeconds,
    MissionClock,
    NonEmptyText,
    ProtocolState,
    TelemetrySample,
)

_SECONDS = TypeAdapter(METSeconds)
_IDENTIFIER = TypeAdapter(NonEmptyText)
_Model = TypeVar("_Model", bound=Contract)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS missions (
    mission_id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS episodes (
    episode_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions,
    subject_id TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS telemetry (
    sample_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions,
    subject_id TEXT NOT NULL,
    met_seconds INTEGER NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS telemetry_window
ON telemetry (mission_id, subject_id, met_seconds, sample_id);
CREATE TABLE IF NOT EXISTS clinical_events (
    event_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions,
    episode_id TEXT NOT NULL REFERENCES episodes,
    met_seconds INTEGER NOT NULL,
    pending INTEGER NOT NULL CHECK (pending IN (0, 1)),
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_pending
ON clinical_events (mission_id, pending, met_seconds, event_id);
CREATE INDEX IF NOT EXISTS events_episode
ON clinical_events (episode_id, pending, met_seconds, event_id);
CREATE TABLE IF NOT EXISTS clinical_findings (
    episode_id TEXT NOT NULL REFERENCES episodes,
    finding_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    met_seconds INTEGER NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (episode_id, finding_id, revision)
);
CREATE TABLE IF NOT EXISTS assessment_turns (
    episode_id TEXT NOT NULL REFERENCES episodes,
    turn_id TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (episode_id, turn_id)
);
CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions,
    episode_id TEXT NOT NULL REFERENCES episodes,
    direction TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'delivered')),
    deliver_at_met_seconds INTEGER NOT NULL,
    delivered_met_seconds INTEGER,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS messages_due
ON messages (mission_id, status, deliver_at_met_seconds, message_id);
CREATE INDEX IF NOT EXISTS messages_inbox
ON messages (mission_id, direction, status, delivered_met_seconds, message_id);
CREATE TABLE IF NOT EXISTS clock_commands (
    mission_id TEXT NOT NULL REFERENCES missions,
    command_id TEXT NOT NULL,
    seconds INTEGER NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (mission_id, command_id)
);
"""


def _decode(row: sqlite3.Row | None, model: type[_Model], identifier: str) -> _Model:
    if row is None:
        raise KeyError(identifier)
    return model.model_validate_json(row["data"])


class SpaceLinkDB:
    """One SQLite connection per worker. Use as a context manager to close it."""

    def __init__(self, path: str | Path):
        self._db = sqlite3.connect(path, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._savepoint = 0
        self._advancing = False
        try:
            self._db.execute("PRAGMA foreign_keys = ON")
            self._db.executescript("BEGIN IMMEDIATE;\n" + _SCHEMA + "\nCOMMIT;")
        except BaseException:
            self._db.close()
            raise

    def __enter__(self) -> "SpaceLinkDB":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._db.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Group writes atomically, for example when opening an episode."""
        if not self._db.in_transaction:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield
                self._db.commit()
            except BaseException:
                self._db.rollback()
                raise
            return

        self._savepoint += 1
        name = f"patch_{self._savepoint}"
        self._db.execute(f"SAVEPOINT {name}")
        try:
            yield
        except BaseException:
            self._db.execute(f"ROLLBACK TO {name}")
            raise
        finally:
            self._db.execute(f"RELEASE {name}")

    def create_mission(self, clock: MissionClock) -> MissionClock:
        with self.transaction():
            row = self._db.execute(
                "SELECT data FROM missions WHERE mission_id = ?", (clock.mission_id,)
            ).fetchone()
            if row is not None:
                existing = MissionClock.model_validate_json(row["data"])
                if (
                    existing.scenario_id != clock.scenario_id
                    or existing.one_way_delay_seconds != clock.one_way_delay_seconds
                ):
                    raise ValueError("Mission ID is already in use with different settings.")
                return existing
            self._db.execute(
                "INSERT INTO missions VALUES (?, ?)", (clock.mission_id, clock.model_dump_json())
            )
            return clock

    def get_mission_clock(self, mission_id: str) -> MissionClock:
        row = self._db.execute(
            "SELECT data FROM missions WHERE mission_id = ?", (mission_id,)
        ).fetchone()
        return _decode(row, MissionClock, mission_id)

    def _update_clock(self, clock: MissionClock, **changes: object) -> MissionClock:
        data = clock.model_dump()
        if all(data[field] == value for field, value in changes.items()):
            return clock
        updated = MissionClock.model_validate(data | changes | {"version": clock.version + 1})
        self._db.execute(
            "UPDATE missions SET data = ? WHERE mission_id = ?",
            (updated.model_dump_json(), updated.mission_id),
        )
        return updated

    def set_link_status(self, mission_id: str, status: LinkStatus | str) -> MissionClock:
        with self.transaction():
            return self._update_clock(self.get_mission_clock(mission_id), link_status=LinkStatus(status))

    def _episode(self, episode_id: str) -> sqlite3.Row:
        row = self._db.execute(
            "SELECT * FROM episodes WHERE episode_id = ?", (episode_id,)
        ).fetchone()
        if row is None:
            raise KeyError(episode_id)
        return row

    def get_protocol_state(self, episode_id: str) -> ProtocolState:
        return ProtocolState.model_validate_json(self._episode(episode_id)["data"])

    def save_protocol_state(self, mission_id: str, subject_id: str, state: ProtocolState) -> None:
        subject_id = _IDENTIFIER.validate_python(subject_id)
        with self.transaction():
            clock = self.get_mission_clock(mission_id)
            if state.updated_at_met_seconds > clock.met_seconds:
                raise ValueError("An episode state cannot be recorded in the future.")
            row = self._db.execute(
                "SELECT * FROM episodes WHERE episode_id = ?", (state.episode_id,)
            ).fetchone()
            if row is None:
                self._db.execute(
                    "INSERT INTO episodes VALUES (?, ?, ?, ?)",
                    (state.episode_id, mission_id, subject_id, state.model_dump_json()),
                )
                return
            if (row["mission_id"], row["subject_id"]) != (mission_id, subject_id):
                raise ValueError("Episode ID already belongs to another mission or subject.")
            previous = ProtocolState.model_validate_json(row["data"])
            if state == previous:
                return
            if (
                state.state_version <= previous.state_version
                or state.updated_at_met_seconds < previous.updated_at_met_seconds
            ):
                raise ValueError("Updated episode states require a newer revision and monotonic MET.")
            self._db.execute(
                "UPDATE episodes SET data = ? WHERE episode_id = ?",
                (state.model_dump_json(), state.episode_id),
            )

    def record_telemetry(self, sample: TelemetrySample) -> None:
        with self.transaction():
            clock = self.get_mission_clock(sample.mission_id)
            if sample.met_seconds > clock.met_seconds:
                raise ValueError("Telemetry cannot be recorded in the future.")
            self._db.execute(
                "INSERT INTO telemetry VALUES (?, ?, ?, ?, ?) ON CONFLICT(sample_id) DO NOTHING",
                (
                    sample.sample_id, sample.mission_id, sample.subject_id,
                    sample.met_seconds, sample.model_dump_json(),
                ),
            )
            row = self._db.execute(
                "SELECT data FROM telemetry WHERE sample_id = ?", (sample.sample_id,)
            ).fetchone()
            if TelemetrySample.model_validate_json(row["data"]) != sample:
                raise ValueError("Telemetry ID already refers to a different sample.")

    def recent_telemetry(
        self, mission_id: str, subject_id: str, *,
        at_met_seconds: int | None = None, window_seconds: int = 60 * 60,
    ) -> list[TelemetrySample]:
        clock = self.get_mission_clock(mission_id)
        end = clock.met_seconds if at_met_seconds is None else _SECONDS.validate_python(at_met_seconds)
        window = _SECONDS.validate_python(window_seconds)
        if end > clock.met_seconds:
            raise ValueError("Telemetry history cannot include future samples.")
        rows = self._db.execute(
            """SELECT data FROM telemetry WHERE mission_id = ? AND subject_id = ?
               AND met_seconds BETWEEN ? AND ? ORDER BY met_seconds, sample_id""",
            (mission_id, subject_id, max(0, end - window), end),
        )
        return [TelemetrySample.model_validate_json(row["data"]) for row in rows]

    def _store_event(self, event: ClinicalEvent, *, pending: bool) -> None:
        with self.transaction():
            row = self._db.execute(
                "SELECT data, pending FROM clinical_events WHERE event_id = ?", (event.event_id,)
            ).fetchone()
            if row is not None:
                if ClinicalEvent.model_validate_json(row["data"]) != event:
                    raise ValueError("Event ID already refers to a different event.")
                if row["pending"] and not pending:
                    raise ValueError("Scheduled events are recorded by the clock advance.")
                return
            mission_id = self._episode(event.episode_id)["mission_id"]
            now = self.get_mission_clock(mission_id).met_seconds
            if pending and event.met_seconds < now:
                raise ValueError("An event cannot be scheduled in the past.")
            if pending and self._advancing and event.met_seconds == now:
                raise ValueError("An event handler can only schedule follow-up events at a later MET.")
            if not pending and event.met_seconds > now:
                raise ValueError("Future events must be scheduled before they can be recorded.")
            self._db.execute(
                "INSERT INTO clinical_events VALUES (?, ?, ?, ?, ?, ?)",
                (
                    event.event_id, mission_id, event.episode_id,
                    event.met_seconds, pending, event.model_dump_json(),
                ),
            )

    def record_event(self, event: ClinicalEvent) -> None:
        self._store_event(event, pending=False)

    def schedule_event(self, event: ClinicalEvent) -> None:
        self._store_event(event, pending=True)

    def list_events(self, episode_id: str) -> list[ClinicalEvent]:
        rows = self._db.execute(
            """SELECT data FROM clinical_events
               WHERE episode_id = ? AND pending = 0 ORDER BY met_seconds, event_id""",
            (episode_id,),
        )
        return [ClinicalEvent.model_validate_json(row["data"]) for row in rows]

    def record_finding(self, finding_id: str, finding: ClinicalFinding) -> None:
        finding_id = _IDENTIFIER.validate_python(finding_id)
        with self.transaction():
            now = self.get_mission_clock(self._episode(finding.episode_id)["mission_id"]).met_seconds
            if finding.met_seconds > now:
                raise ValueError("A finding cannot be recorded in the future.")
            key = (finding.episode_id, finding_id, finding.revision)
            self._db.execute(
                """INSERT INTO clinical_findings VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(episode_id, finding_id, revision) DO NOTHING""",
                (*key, finding.met_seconds, finding.model_dump_json()),
            )
            row = self._db.execute(
                """SELECT data FROM clinical_findings
                   WHERE episode_id = ? AND finding_id = ? AND revision = ?""",
                key,
            ).fetchone()
            if ClinicalFinding.model_validate_json(row["data"]) != finding:
                raise ValueError("Finding revision already refers to different content.")

    def list_findings(self, episode_id: str) -> list[ClinicalFinding]:
        """Return all recorded revisions in chronological order."""
        rows = self._db.execute(
            """SELECT data FROM clinical_findings
               WHERE episode_id = ? ORDER BY met_seconds, finding_id, revision""",
            (episode_id,),
        )
        return [ClinicalFinding.model_validate_json(row["data"]) for row in rows]

    def record_assessment_turn(self, turn: ClinicalAssessmentTurn) -> None:
        """Persist a turn after the controller has validated its sources."""
        with self.transaction():
            key = (turn.episode_id, turn.turn_id)
            self._db.execute(
                """INSERT INTO assessment_turns VALUES (?, ?, ?)
                   ON CONFLICT(episode_id, turn_id) DO NOTHING""",
                (*key, turn.model_dump_json()),
            )
            if self.get_assessment_turn(*key) != turn:
                raise ValueError("Assessment turn ID already refers to different content.")

    def get_assessment_turn(self, episode_id: str, turn_id: str) -> ClinicalAssessmentTurn:
        row = self._db.execute(
            "SELECT data FROM assessment_turns WHERE episode_id = ? AND turn_id = ?",
            (episode_id, turn_id),
        ).fetchone()
        return _decode(row, ClinicalAssessmentTurn, turn_id)

    def queue_message(
        self, *, message_id: str, episode_id: str, direction: MessageDirection | str,
        kind: MessageKind | str, payload: Mapping[str, JsonValue],
        source_state_version: int | None = None,
    ) -> MedicalMessage:
        """Capture the payload and compute the ETA from the persisted mission clock."""
        message_id = _IDENTIFIER.validate_python(message_id)
        episode_id = _IDENTIFIER.validate_python(episode_id)
        with self.transaction():
            row = self._db.execute(
                "SELECT data FROM messages WHERE message_id = ?", (message_id,)
            ).fetchone()
            previous = MedicalMessage.model_validate_json(row["data"]) if row else None
            clock = self.get_mission_clock(self._episode(episode_id)["mission_id"])
            sent = previous.created_met_seconds if previous else clock.met_seconds
            eta = previous.deliver_at_met_seconds if previous else sent + clock.one_way_delay_seconds
            message = MedicalMessage(
                message_id=message_id, episode_id=episode_id, direction=direction, kind=kind,
                created_met_seconds=sent, deliver_at_met_seconds=eta, payload=payload,
                source_state_version=source_state_version,
                status=previous.status if previous else MessageStatus.QUEUED,
                delivered_met_seconds=previous.delivered_met_seconds if previous else None,
            )
            if previous is not None:
                if message != previous:
                    raise ValueError("Message ID already refers to a different message.")
                return previous
            if message.kind == MessageKind.ACK:
                self._validate_ack(message)

            self._db.execute(
                "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    message.message_id, clock.mission_id, message.episode_id, message.direction,
                    message.status, message.deliver_at_met_seconds,
                    message.delivered_met_seconds, message.model_dump_json(),
                ),
            )
            return message

    def _validate_ack(self, message: MedicalMessage) -> None:
        reference = AckPayload.model_validate(message.payload).acknowledged_message_id
        row = self._db.execute("SELECT data FROM messages WHERE message_id = ?", (reference,)).fetchone()
        original = MedicalMessage.model_validate_json(row["data"]) if row else None
        if (
            original is None
            or original.episode_id != message.episode_id
            or original.direction != MessageDirection.SHIP_TO_EARTH
            or original.delivered_met_seconds is None
            or original.delivered_met_seconds > message.created_met_seconds
        ):
            raise ValueError("An ACK must refer to a message already delivered to Earth for this episode.")

    def list_messages(self, mission_id: str) -> list[MedicalMessage]:
        """List queued and delivered messages for the simulator operator."""
        rows = self._db.execute(
            """SELECT data FROM messages
               WHERE mission_id = ? ORDER BY deliver_at_met_seconds, message_id""",
            (mission_id,),
        )
        return [MedicalMessage.model_validate_json(row["data"]) for row in rows]

    def inbox(self, mission_id: str, direction: MessageDirection | str) -> list[MedicalMessage]:
        """Return only delivered traffic in the requested direction."""
        rows = self._db.execute(
            """SELECT data FROM messages WHERE mission_id = ? AND direction = ?
               AND status = 'delivered' ORDER BY delivered_met_seconds, deliver_at_met_seconds, message_id""",
            (mission_id, MessageDirection(direction)),
        )
        return [MedicalMessage.model_validate_json(row["data"]) for row in rows]

    def _deliver_until(self, clock: MissionClock, through_met: int) -> list[MedicalMessage]:
        if clock.link_status != LinkStatus.CONNECTED or through_met < clock.met_seconds:
            return []
        rows = self._db.execute(
            """SELECT data FROM messages WHERE mission_id = ? AND status = 'queued'
               AND deliver_at_met_seconds <= ? ORDER BY deliver_at_met_seconds, message_id""",
            (clock.mission_id, through_met),
        ).fetchall()
        delivered = []
        for row in rows:
            message = MedicalMessage.model_validate_json(row["data"])
            actual = max(clock.met_seconds, message.deliver_at_met_seconds)
            arrival = MedicalMessage.model_validate(
                message.model_dump() | {"status": MessageStatus.DELIVERED, "delivered_met_seconds": actual}
            )
            self._db.execute(
                "UPDATE messages SET status = ?, delivered_met_seconds = ?, data = ? WHERE message_id = ?",
                (arrival.status, actual, arrival.model_dump_json(), arrival.message_id),
            )
            delivered.append(arrival)
        return delivered

    def deliver_due_messages(self, mission_id: str) -> list[MedicalMessage]:
        """Deliver due messages at the current MET, also after an explicit reconnect."""
        with self.transaction():
            clock = self.get_mission_clock(mission_id)
            return self._deliver_until(clock, clock.met_seconds)

    def advance_mission_clock(
        self, mission_id: str, seconds: int, *, command_id: str,
        process_event: Callable[[ClinicalEvent], None] | None = None,
    ) -> MissionClock:
        """Advance MET atomically and replay the original result for a repeated command.

        A scheduled event is recorded before its handler runs. The handler may
        write state and queue messages on this connection. Its database writes
        roll back with the command if it fails. Events at a given MET run before
        automatic delivery at that MET.
        """
        seconds = _SECONDS.validate_python(seconds)
        command_id = _IDENTIFIER.validate_python(command_id)
        if self._advancing:
            raise RuntimeError("An event handler cannot advance the clock recursively.")
        with self.transaction():
            row = self._db.execute(
                "SELECT seconds, data FROM clock_commands WHERE mission_id = ? AND command_id = ?",
                (mission_id, command_id),
            ).fetchone()
            if row is not None:
                if row["seconds"] != seconds:
                    raise ValueError("Clock command ID already refers to a different advance.")
                return MissionClock.model_validate_json(row["data"])

            clock = self.get_mission_clock(mission_id)
            target = clock.met_seconds + seconds
            self._advancing = True
            try:
                clock = self._advance_interval(clock, target, process_event)
            finally:
                self._advancing = False
            self._db.execute(
                "INSERT INTO clock_commands VALUES (?, ?, ?, ?)",
                (mission_id, command_id, seconds, clock.model_dump_json()),
            )
            return clock

    def _advance_interval(
        self, clock: MissionClock, target: int, process_event: Callable[[ClinicalEvent], None] | None,
    ) -> MissionClock:
        while True:
            next_event = self._db.execute(
                """SELECT met_seconds FROM clinical_events WHERE mission_id = ?
                   AND pending = 1 AND met_seconds <= ? ORDER BY met_seconds LIMIT 1""",
                (clock.mission_id, target),
            ).fetchone()
            if next_event is None:
                self._deliver_until(clock, target)
                return self._update_clock(clock, met_seconds=target)
            if process_event is None:
                raise ValueError("A handler is required to process scheduled events in this interval.")

            met = next_event["met_seconds"]
            self._deliver_until(clock, met - 1)
            clock = self._update_clock(clock, met_seconds=met)
            events = self._db.execute(
                """SELECT event_id, data FROM clinical_events WHERE mission_id = ?
                   AND pending = 1 AND met_seconds = ? ORDER BY event_id""",
                (clock.mission_id, met),
            ).fetchall()
            for row in events:
                event = ClinicalEvent.model_validate_json(row["data"])
                self._db.execute(
                    "UPDATE clinical_events SET pending = 0 WHERE event_id = ?", (event.event_id,)
                )
                process_event(event)
            clock = self.get_mission_clock(clock.mission_id)
