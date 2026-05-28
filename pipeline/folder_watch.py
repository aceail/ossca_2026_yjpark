"""Wave 2 — Folder snapshot loop.

For every open Task with a folder_path, ask the configured FolderProvider for
a current snapshot and INSERT into FolderSnapshot. Called both from a
background asyncio loop (backend lifespan) and ad-hoc from tests/scripts.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

from core.providers import FolderProvider, get_folder_provider


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_host_path(path: str) -> str:
    """Expand a user-typed path so it points at the host's filesystem when
    backend runs inside a container.

    compose mounts ${HOME}:${HOME}:ro and sets HOST_HOME=${HOME} so the
    host's home dir is visible at the same absolute path inside the
    container. Tilde and the literal '$HOME' are expanded against
    HOST_HOME, not the container's own root home, so '~/Desktop/work'
    typed by a host user resolves to e.g. '/home/gpuuser/Desktop/work'
    instead of '/root/Desktop/work'.
    """
    if not path:
        return path
    host_home = os.environ.get("HOST_HOME") or os.path.expanduser("~")
    if path.startswith("~/"):
        return os.path.join(host_home, path[2:])
    if path == "~":
        return host_home
    if path.startswith("$HOME/"):
        return os.path.join(host_home, path[len("$HOME/"):])
    return path


def scan_open_tasks(
    conn: sqlite3.Connection,
    *,
    provider: FolderProvider | None = None,
) -> int:
    """모든 open task의 folder_path를 스냅샷해 FolderSnapshot에 적재.

    Returns 적재된 row 수. provider=None이면 factory가 NAEIL_MODE로 결정.
    """
    fp = provider or get_folder_provider()
    rows = conn.execute(
        """SELECT id, folder_path FROM Task
           WHERE status = 'open' AND folder_path IS NOT NULL AND folder_path != ''"""
    ).fetchall()

    inserted = 0
    for row in rows:
        resolved = _resolve_host_path(row["folder_path"])
        snap = fp.snapshot(resolved)
        if snap is None:
            continue
        conn.execute(
            """INSERT INTO FolderSnapshot
               (task_id, taken_at, file_count, total_bytes, newest_mtime, files_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                row["id"],
                _now_iso(),
                snap.file_count,
                snap.total_bytes,
                snap.newest_mtime,
                json.dumps(snap.files, ensure_ascii=False),
            ),
        )
        inserted += 1
    if inserted:
        conn.commit()
    return inserted
