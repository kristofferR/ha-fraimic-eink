"""SQLite transport journal. Call from an executor under the service lock."""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import asdict
from pathlib import Path

from .model import Job


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> tuple[dict[str, Job], dict[str, int | None], dict[str, dict[str, object]]]:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with sqlite3.connect(self.path) as db:
            os.chmod(self.path, 0o600)
            db.execute("PRAGMA secure_delete=ON")
            db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, meta TEXT NOT NULL, audio BLOB NOT NULL, asset BLOB NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS devices (id TEXT PRIMARY KEY, wake INTEGER)")
            db.execute("CREATE TABLE IF NOT EXISTS telemetry (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS enrollment (id TEXT PRIMARY KEY, binding TEXT NOT NULL)")
            jobs = {}
            for ident, meta, audio, asset in db.execute("SELECT id, meta, audio, asset FROM jobs"):
                jobs[ident] = Job(**json.loads(meta), audio=audio, asset=asset)
            wakes = dict(db.execute("SELECT id, wake FROM devices"))
            telemetry = {ident: json.loads(data) for ident, data in db.execute("SELECT id, data FROM telemetry")}
        return jobs, wakes, telemetry

    def enroll(self, device: str, binding: str) -> None:
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT binding FROM enrollment WHERE id = ?", (device,)).fetchone()
            if row is not None and row[0] != binding:
                raise ValueError("An enrolled device identity/model changed; use a new device ID")
            db.execute("INSERT OR IGNORE INTO enrollment VALUES (?, ?)", (device, binding))

    def telemetry(self, device: str, data: dict[str, object]) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT OR REPLACE INTO telemetry VALUES (?, ?)", (device, json.dumps(data)))

    def save(self, job: Job) -> None:
        meta = asdict(job)
        audio, asset = meta.pop("audio"), meta.pop("asset")
        with sqlite3.connect(self.path) as db:
            db.execute("PRAGMA secure_delete=ON")
            db.execute("INSERT OR REPLACE INTO jobs VALUES (?, ?, ?, ?)",
                       (job.id, json.dumps(meta, separators=(",", ":")), audio, asset))

    def wake(self, device: str, timestamp: int | None) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT OR REPLACE INTO devices VALUES (?, ?)", (device, timestamp))

    def delete(self, ident: str) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute("PRAGMA secure_delete=ON")
            db.execute("DELETE FROM jobs WHERE id = ?", (ident,))
