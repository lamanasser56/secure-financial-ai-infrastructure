"""Unwired local durable audit prototype. Only existing sanitized tool events."""

import json
import os
from pathlib import Path
import sqlite3
import stat
import threading

from runtime.phase3.trusted_runtime import ControlFailure
from runtime.phase4.tool_audit import validate_ai_audit_event


def _fail():
    raise ControlFailure("audit", "invalid_event")


class DurableToolAudit:
    """Private SQLite journal with bounded closed events and commit-before-return.

    One trusted process owns the private directory. No raw text, exception,
    argument, result, key, credential or provider response is admitted. This
    proves local reopen/commit behavior only, not remote retention, tamper proof,
    encryption, hardware durability or qualification of a deployed audit sink.
    """

    def __init__(self, directory, *, maximum=256):
        self._db = None
        try:
            if type(maximum) is not int or not 1 <= maximum <= 256:
                _fail()
            self._directory = Path(directory).absolute()
            if any(p.is_symlink() for p in (self._directory, *self._directory.parents)):
                _fail()
            info = self._directory.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o700):
                _fail()
            self._path = self._directory / "tool-audit.sqlite"
            if not self._path.exists() and not self._path.is_symlink():
                fd = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
                os.close(fd)
                directory_fd = os.open(self._directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            self._check_files()
            self._db = sqlite3.connect(self._path, timeout=1, check_same_thread=False)
            self._db.execute("PRAGMA journal_mode=DELETE")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.execute("PRAGMA trusted_schema=OFF")
            self._db.execute("PRAGMA max_page_count=512")
            if self._db.execute("PRAGMA synchronous").fetchone()[0] != 2:
                _fail()
            self._db.execute("CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, event TEXT NOT NULL)")
            self._db.commit()
            self._maximum, self._lock = maximum, threading.Lock()
            self._check_files()
            # Reopen validates all historical entries before future dispatches.
            rows = self._db.execute("SELECT id,event FROM events ORDER BY rowid").fetchall()
            if len(rows) > maximum:
                _fail()
            for identifier, encoded in rows:
                event = validate_ai_audit_event(json.loads(encoded))
                if identifier != event["event_id"] or self._encode(event) != encoded:
                    _fail()
        except Exception:
            if self._db is not None:
                self._db.close()
            _fail()

    def _check_files(self):
        directory = self._directory.lstat()
        if stat.S_IMODE(directory.st_mode) != 0o700 or directory.st_uid != os.getuid():
            _fail()
        for path in self._directory.iterdir():
            if path.name not in {"tool-audit.sqlite", "tool-audit.sqlite-journal"}:
                _fail()
            info = path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_size > 2_097_152):
                _fail()

    @staticmethod
    def _encode(event):
        encoded = json.dumps(validate_ai_audit_event(event), sort_keys=True, separators=(",", ":"))
        if len(encoded.encode()) > 4096:
            _fail()
        return encoded

    def append(self, event):
        """Return only after committed admission. Caller must block on failure.

        Duplicate/replayed IDs and full journals block. No silent dropping or
        pruning, automatic retries, or execution of callbacks/tools occurs here.
        """
        try:
            encoded = self._encode(event)
            with self._lock:
                self._check_files()
                self._db.execute("BEGIN IMMEDIATE")
                if self._db.execute("SELECT COUNT(*) FROM events").fetchone()[0] >= self._maximum:
                    _fail()
                self._db.execute("INSERT INTO events VALUES (?,?)", (event["event_id"], encoded))
                self._db.commit()
                self._check_files()
        except Exception:
            try:
                self._db.rollback()
            except Exception:
                pass
            _fail()

    def close(self):
        self._db.close()
