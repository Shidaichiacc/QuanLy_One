"""Database credential validation and JX configuration synchronization."""

from __future__ import annotations

import os
import re
from pathlib import Path

from jx_password import encrypt_password


PASSWORD_RE = re.compile(r"^(?=.{12,20}$)(?=.*[a-z])(?=.*[A-Z])(?=.*[0-9])(?=.*[@_!.-])[A-Za-z0-9@_!.-]+$")


def validate_database_password(value, label="Mật khẩu"):
    if not PASSWORD_RE.fullmatch(value or ""):
        raise ValueError(
            f"{label} phải dài 12–20 ký tự, có chữ hoa, chữ thường, số và ít nhất "
            "một ký tự @ _ ! . hoặc -"
        )
    return value


def read_env(path):
    values = {}
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def write_env(path, updates):
    path = Path(path)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    remaining = dict(updates)
    output = []
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in remaining:
                output.append(f"{key}={remaining.pop(key)}")
                continue
        output.append(line)
    if output and output[-1]:
        output.append("")
    output.extend(f"{key}={value}" for key, value in remaining.items())
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _replace_ini_values(path, replacements, snapshots):
    """Replace {(section, key): value}, preserving bytes/newlines and file mode."""
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        return 0
    raw = path.read_bytes()
    text = raw.decode("latin-1")
    section = ""
    changed = 0
    output = []
    section_pattern = re.compile(r"^\s*\[([^]]+)]")
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        ending = line[len(body):]
        match = section_pattern.match(body)
        if match:
            section = match.group(1).strip().casefold()
            output.append(line)
            continue
        replaced = False
        for (wanted_section, wanted_key), value in replacements.items():
            if section != wanted_section.casefold():
                continue
            key_match = re.match(rf"^(\s*{re.escape(wanted_key)}\s*=\s*).*$", body, re.IGNORECASE)
            if key_match:
                new_line = key_match.group(1) + value + ending
                output.append(new_line)
                changed += int(new_line != line)
                replaced = True
                break
        if not replaced:
            output.append(line)
    updated = "".join(output).encode("latin-1")
    if updated != raw:
        snapshots.setdefault(path, raw)
        temporary = path.with_name(path.name + ".db-password.tmp")
        temporary.write_bytes(updated)
        os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    return changed


def _safe_config_files(root, filename):
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        return []
    resolved_root = root.resolve()
    result = []
    for path in root.rglob(filename):
        try:
            if path.is_symlink() or not path.is_file():
                continue
            path.resolve().relative_to(resolved_root)
            result.append(path)
        except (OSError, ValueError):
            continue
    return result


def patch_server_credentials(server_root, mysql_password, mssql_password, snapshots=None):
    snapshots = snapshots if snapshots is not None else {}
    mysql_encoded = encrypt_password(mysql_password)
    mssql_encoded = encrypt_password(mssql_password)
    changed = 0
    for path in _safe_config_files(server_root, "goddess.cfg"):
        changed += _replace_ini_values(
            path, {("Database", "Password"): mysql_encoded}, snapshots
        )
    # Goddess và S3Relay dùng cùng database MySQL `server1`, nhưng mật khẩu
    # nằm ở các file riêng. Bỏ sót relay_config.ini khiến Start All dừng tại
    # S3Relay dù container MySQL và Goddess vẫn hoạt động bình thường.
    for filename in ("relay_config.ini", "backupdaemon.ini"):
        for path in _safe_config_files(server_root, filename):
            changed += _replace_ini_values(
                path, {("Database", "Password"): mysql_encoded}, snapshots
            )
    for path in _safe_config_files(server_root, "database.ini"):
        changed += _replace_ini_values(
            path,
            {
                ("card", "PassWord"): mssql_encoded,
                ("account", "PassWord"): mssql_encoded,
            },
            snapshots,
        )
    return changed, snapshots


def patch_all_credentials(project_root, mysql_password, mssql_password, snapshots=None):
    project_root = Path(project_root)
    snapshots = snapshots if snapshots is not None else {}
    changed = _replace_ini_values(
        project_root / "JX_Servers" / "Config" / "mssql.ini",
        {("mssql", "password"): mssql_password},
        snapshots,
    )
    versions = project_root / "JX_Servers" / "JX_Versions"
    if versions.is_dir():
        for version in versions.iterdir():
            if version.is_dir() and not version.is_symlink():
                current, _ = patch_server_credentials(version, mysql_password, mssql_password, snapshots)
                changed += current
    return changed, snapshots


def restore_snapshots(snapshots):
    errors = []
    for path, content in snapshots.items():
        try:
            temporary = path.with_name(path.name + ".rollback.tmp")
            temporary.write_bytes(content)
            mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
            os.chmod(temporary, mode)
            os.replace(temporary, path)
        except OSError as exc:
            errors.append(f"{path}: {exc}")
    return errors
