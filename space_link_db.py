"""SQLite storage and one-way transport for the current PATCH MVP.

Payloads and evidence are immutable. Only transport metadata and episode state
are updated. An old scaffold database is not silently reused or migrated.
"""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from contracts import MedicalMessage, MessageStatus


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id TEXT NOT NULL UNIQUE,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    episode_id TEXT NOT NULL REFERENCES episodes(episode_id),
    t_sim INTEGER NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS observations (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_id TEXT NOT NULL UNIQUE,
    episode_id TEXT NOT NULL REFERENCES episodes(episode_id),
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS telemetry_samples (
    sample_id TEXT PRIMARY KEY,
    episode_id TEXT NOT NULL REFERENCES episodes(episode_id),
    observed_at_sim INTEGER NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS telemetry_window ON telemetry_samples(episode_id, observed_at_sim);
CREATE TABLE IF NOT EXISTS packets (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    packet_id TEXT NOT NULL UNIQUE,
    episode_id TEXT NOT NULL REFERENCES episodes(episode_id),
    payload_json TEXT NOT NULL,
    transport_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS commands (
    command_id TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    result TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS immutable_events BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'Events are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_observations BEFORE UPDATE ON observations
BEGIN SELECT RAISE(ABORT, 'Observations are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_payload BEFORE UPDATE OF payload_json ON packets
BEGIN SELECT RAISE(ABORT, 'Packet payloads are immutable'); END;
"""


class SpaceLinkDB:
    def __init__(self, path: str | Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path), isolation_level=None, timeout=15)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript(SCHEMA)
        self._depth = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.connection.close()

    @contextmanager
    def transaction(self):
        depth = self._depth
        self.connection.execute("BEGIN IMMEDIATE" if depth == 0 else f"SAVEPOINT sp_{depth}")
        self._depth += 1
        try:
            yield
        except BaseException:
            self.connection.execute("ROLLBACK" if depth == 0 else f"ROLLBACK TO sp_{depth}")
            if depth:
                self.connection.execute(f"RELEASE sp_{depth}")
            raise
        else:
            self.connection.execute("COMMIT" if depth == 0 else f"RELEASE sp_{depth}")
        finally:
            self._depth -= 1

    def execute_command(self, command_id: str, fingerprint: str, callback):
        with self.transaction():
            previous = self.connection.execute("SELECT * FROM commands WHERE command_id=?", (command_id,)).fetchone()
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise ValueError("Identificador de comando reutilizado con otra acción.")
                return json.loads(previous["result"])
            result = callback()
            self.connection.execute("INSERT INTO commands VALUES(?,?,?)", (command_id, fingerprint, encode(result)))
            return result

    def insert_episode(self, episode: dict):
        self.connection.execute("INSERT INTO episodes(episode_id,data) VALUES(?,?)", (episode["episode_id"], encode(episode)))
        self.set_setting("active_episode", episode["episode_id"])

    def save_episode(self, episode: dict):
        self.connection.execute("UPDATE episodes SET data=? WHERE episode_id=?", (encode(episode), episode["episode_id"]))

    def get_episode(self, episode_id: str) -> dict:
        row = self.connection.execute("SELECT data FROM episodes WHERE episode_id=?", (episode_id,)).fetchone()
        if not row:
            raise ValueError("El episodio no existe.")
        return json.loads(row["data"])

    def list_episodes(self) -> list[dict]:
        return [json.loads(r[0]) for r in self.connection.execute("SELECT data FROM episodes ORDER BY seq DESC")]

    def set_setting(self, key: str, value: str):
        self.connection.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    def get_setting(self, key: str):
        row = self.connection.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def record_event(self, event):
        self.connection.execute("INSERT INTO events(event_id,episode_id,t_sim,data) VALUES(?,?,?,?)",
            (event.event_id, event.episode_id, event.t_sim, event.model_dump_json()))

    def record_observation(self, observation):
        self.connection.execute("INSERT INTO observations(observation_id,episode_id,data) VALUES(?,?,?)",
            (observation.observation_id, observation.episode_id, observation.model_dump_json()))

    def record_telemetry(self, sample):
        self.connection.execute("INSERT INTO telemetry_samples VALUES(?,?,?,?)",
            (sample.sample_id, sample.episode_id, sample.observed_at_sim, sample.model_dump_json()))

    def events(self, episode_id):
        return [json.loads(r[0]) for r in self.connection.execute("SELECT data FROM events WHERE episode_id=? ORDER BY t_sim,seq", (episode_id,))]

    def observations(self, episode_id):
        return [json.loads(r[0]) for r in self.connection.execute("SELECT data FROM observations WHERE episode_id=? ORDER BY seq", (episode_id,))]

    def telemetry(self, episode_id, start, end):
        return [json.loads(r[0]) for r in self.connection.execute(
            "SELECT data FROM telemetry_samples WHERE episode_id=? AND observed_at_sim BETWEEN ? AND ? ORDER BY observed_at_sim,rowid", (episode_id, start, end))]

    def create_packet(self, packet: MedicalMessage):
        data = packet.model_dump(mode="json")
        payload = data.pop("payload")
        self.connection.execute("INSERT INTO packets(packet_id,episode_id,payload_json,transport_json) VALUES(?,?,?,?)",
            (packet.packet_id, packet.episode_id, encode(payload), encode(data)))

    def packets(self, episode_id, delivered_only=False):
        records = self.connection.execute("SELECT payload_json,transport_json FROM packets WHERE episode_id=? ORDER BY seq", (episode_id,))
        result = []
        for row in records:
            item = json.loads(row["transport_json"])
            if not delivered_only or item["status"] == MessageStatus.DELIVERED:
                result.append(item | {"payload": json.loads(row["payload_json"])})
        return result

    def process_transport(self, episode_id: str, now: int, link_up: bool, delay_seconds: int):
        """Already-transmitted packets arrive even while the transmitter is DOWN."""
        for packet in self.packets(episode_id):
            payload = packet.pop("payload")
            changed = False
            if packet["status"] == MessageStatus.QUEUED and link_up:
                packet.update(status=MessageStatus.IN_TRANSIT, sent_at_sim=now, arrives_at_sim=now + delay_seconds)
                changed = True
            if packet["status"] == MessageStatus.IN_TRANSIT and packet["arrives_at_sim"] <= now:
                packet.update(status=MessageStatus.DELIVERED, delivered_at_sim=packet["arrives_at_sim"])
                changed = True
            if changed:
                MedicalMessage.model_validate(packet | {"payload": payload})
                self.connection.execute("UPDATE packets SET transport_json=? WHERE packet_id=?", (encode(packet), packet["packet_id"]))
