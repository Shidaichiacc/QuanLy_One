"""IP-based login throttling shared by the web panel and the SSH helper."""

from __future__ import annotations

import fcntl
import ipaddress
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


FAILURES_PER_LEVEL = 3
LOCK_DURATIONS = (300, 3600, 86400)
MAX_AUDIT_ROWS = 1000
STALE_IP_SECONDS = 30 * 86400


class AdminLoginSecurity:
    def __init__(self, state_root):
        self.state_root = Path(state_root)
        self.state_file = self.state_root / "admin-login-security.json"
        self.audit_file = self.state_root / "admin-login-audit.jsonl"
        self.lock_file = self.state_root / "admin-login-security.lock"

    @staticmethod
    def normalize_ip(value):
        value = (value or "").strip()
        try:
            return str(ipaddress.ip_address(value))
        except ValueError:
            return "unknown"

    @contextmanager
    def _locked(self):
        self.state_root.mkdir(parents=True, exist_ok=True)
        with self.lock_file.open("a+", encoding="utf-8") as handle:
            os.chmod(self.lock_file, 0o600)
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _load_unlocked(self):
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("ips", {}), dict):
                raise ValueError
        except (OSError, ValueError, TypeError):
            data = {"version": 1, "ips": {}, "last_success": {}}
        data.setdefault("version", 1)
        data.setdefault("ips", {})
        data.setdefault("last_success", {})
        return data

    def _save_unlocked(self, data):
        temporary = self.state_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.state_file)

    def _audit_unlocked(self, event, ip, username="", detail="", now=None):
        row = {
            "time": int(time.time() if now is None else now),
            "ip": self.normalize_ip(ip),
            "username": str(username or "")[:64],
            "event": str(event or "")[:32],
            "detail": str(detail or "")[:160],
        }
        rows = self._recent_unlocked(MAX_AUDIT_ROWS - 1)
        rows.append(row)
        temporary = self.audit_file.with_suffix(".tmp")
        temporary.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in rows), encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.audit_file)

    def _recent_unlocked(self, limit):
        try:
            lines = self.audit_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        rows = []
        for line in lines[-max(1, int(limit)):]:
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)
            except (ValueError, TypeError):
                continue
        return rows

    @staticmethod
    def _entry_status(entry, now):
        locked_until = int(entry.get("locked_until", 0) or 0)
        remaining = max(0, locked_until - int(now))
        return {
            "locked": remaining > 0,
            "remaining": remaining,
            "locked_until": locked_until,
            "level": max(0, min(3, int(entry.get("level", 0) or 0))),
            "failures": max(0, int(entry.get("failures", 0) or 0)),
            "last_failure": int(entry.get("last_failure", 0) or 0),
            "last_success": int(entry.get("last_success", 0) or 0),
        }

    def status(self, ip, now=None):
        now = int(time.time() if now is None else now)
        ip = self.normalize_ip(ip)
        with self._locked():
            data = self._load_unlocked()
            return self._entry_status(data["ips"].get(ip, {}), now)

    def record_failure(self, ip, username="", now=None):
        now = int(time.time() if now is None else now)
        ip = self.normalize_ip(ip)
        with self._locked():
            data = self._load_unlocked()
            entry = data["ips"].setdefault(ip, {})
            status = self._entry_status(entry, now)
            if status["locked"]:
                self._audit_unlocked("blocked", ip, username, "attempt while locked", now)
                return status
            entry["failures"] = status["failures"] + 1
            entry["level"] = status["level"]
            entry["locked_until"] = 0
            entry["last_failure"] = now
            event = "failure"
            detail = f"failure {entry['failures']}/{FAILURES_PER_LEVEL}"
            if entry["failures"] >= FAILURES_PER_LEVEL:
                duration_index = min(entry["level"], len(LOCK_DURATIONS) - 1)
                duration = LOCK_DURATIONS[duration_index]
                entry["level"] = min(3, entry["level"] + 1)
                entry["failures"] = 0
                entry["locked_until"] = now + duration
                event = "locked"
                detail = f"locked {duration}s; level {entry['level']}"
            self._save_unlocked(data)
            self._audit_unlocked(event, ip, username, detail, now)
            return self._entry_status(entry, now)

    def record_blocked(self, ip, username="", now=None):
        now = int(time.time() if now is None else now)
        ip = self.normalize_ip(ip)
        with self._locked():
            data = self._load_unlocked()
            status = self._entry_status(data["ips"].get(ip, {}), now)
            self._audit_unlocked("blocked", ip, username, "attempt while locked", now)
            return status

    def record_csrf_failure(self, ip, username="", now=None):
        now = int(time.time() if now is None else now)
        ip = self.normalize_ip(ip)
        with self._locked():
            self._audit_unlocked("csrf_invalid", ip, username, "invalid login form", now)

    def record_success(self, ip, username="", now=None):
        now = int(time.time() if now is None else now)
        ip = self.normalize_ip(ip)
        with self._locked():
            data = self._load_unlocked()
            entry = data["ips"].setdefault(ip, {})
            entry.update({"level": 0, "failures": 0, "locked_until": 0, "last_success": now})
            data["last_success"] = {"ip": ip, "time": now, "username": str(username or "")[:64]}
            self._cleanup_unlocked(data, now)
            self._save_unlocked(data)
            self._audit_unlocked("success", ip, username, "login successful", now)

    def _cleanup_unlocked(self, data, now):
        for ip, entry in list(data.get("ips", {}).items()):
            latest = max(int(entry.get("last_failure", 0) or 0), int(entry.get("last_success", 0) or 0))
            status = self._entry_status(entry, now)
            if not status["locked"] and not status["failures"] and not status["level"] and latest < now - STALE_IP_SECONDS:
                data["ips"].pop(ip, None)

    def snapshot(self, now=None, audit_limit=50):
        now = int(time.time() if now is None else now)
        with self._locked():
            data = self._load_unlocked()
            self._cleanup_unlocked(data, now)
            self._save_unlocked(data)
            entries = []
            for ip, entry in data["ips"].items():
                row = {"ip": ip, **self._entry_status(entry, now)}
                entries.append(row)
            entries.sort(key=lambda row: (not row["locked"], -row["last_failure"], row["ip"]))
            audit = self._recent_unlocked(audit_limit)
            return {"entries": entries, "last_success": data.get("last_success", {}), "audit": list(reversed(audit))}

    def unlock(self, ip, source="ssh", now=None):
        now = int(time.time() if now is None else now)
        ip = self.normalize_ip(ip)
        if ip == "unknown":
            raise ValueError("Địa chỉ IP không hợp lệ")
        with self._locked():
            data = self._load_unlocked()
            existed = ip in data["ips"]
            if existed:
                data["ips"][ip].update({"level": 0, "failures": 0, "locked_until": 0})
                self._save_unlocked(data)
            self._audit_unlocked("unlocked", ip, "admin", f"source={source}", now)
            return existed

    def unlock_all(self, source="ssh", now=None):
        now = int(time.time() if now is None else now)
        with self._locked():
            data = self._load_unlocked()
            count = 0
            for entry in data["ips"].values():
                status = self._entry_status(entry, now)
                if status["locked"] or status["failures"] or status["level"]:
                    count += 1
                entry.update({"level": 0, "failures": 0, "locked_until": 0})
            self._save_unlocked(data)
            self._audit_unlocked("unlock_all", "unknown", "admin", f"source={source}; count={count}", now)
            return count


def format_timestamp(value):
    if not value:
        return "—"
    return datetime.fromtimestamp(int(value)).astimezone().strftime("%d/%m/%Y %I:%M:%S %p")


def format_duration(seconds):
    seconds = max(0, int(seconds or 0))
    if seconds >= 3600:
        hours, remainder = divmod(seconds, 3600)
        minutes = remainder // 60
        return f"{hours} giờ {minutes} phút" if minutes else f"{hours} giờ"
    if seconds >= 60:
        minutes, remainder = divmod(seconds, 60)
        return f"{minutes} phút {remainder} giây" if remainder else f"{minutes} phút"
    return f"{seconds} giây"
