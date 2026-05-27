"""Folder snapshot providers.

LocalFolderProvider scans the OS directly via os.scandir — only valid when
backend runs on the same machine as the user (default local mode).
RemoteAgentFolderProvider (Wave 5) reads from snapshots a desktop agent
already pushed via /api/tasks/{id}/folder-snapshots; the scan_open_tasks
loop is then a no-op.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class FolderSnapshotData:
    file_count: int
    total_bytes: int
    newest_mtime: str | None              # ISO 8601
    files: list[dict] = field(default_factory=list)  # [{name, size, mtime}]


class FolderProvider(Protocol):
    def snapshot(self, folder_path: str) -> FolderSnapshotData | None: ...


class LocalFolderProvider:
    """os.scandir 한 단계 (recursive=False) — 큰 디렉토리에서도 가벼움.

    파일 단위 mtime + size 누적. symlink는 따라가지 않음.
    folder_path가 없거나 디렉토리 아니면 None 반환 (호출자가 skip).
    """

    def __init__(self, *, max_files: int = 500) -> None:
        self._max_files = max_files

    def snapshot(self, folder_path: str) -> FolderSnapshotData | None:
        if not folder_path:
            return None
        p = Path(folder_path)
        try:
            if not p.exists() or not p.is_dir():
                return None
        except OSError:
            return None

        files: list[dict] = []
        total_bytes = 0
        newest_mtime: str | None = None

        try:
            entries = list(os.scandir(p))
        except OSError:
            return None

        for entry in entries:
            if len(files) >= self._max_files:
                break
            try:
                if not entry.is_file(follow_symlinks=False):
                    continue
                st = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            mtime_iso = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
            files.append({"name": entry.name, "size": st.st_size, "mtime": mtime_iso})
            total_bytes += st.st_size
            if newest_mtime is None or mtime_iso > newest_mtime:
                newest_mtime = mtime_iso

        return FolderSnapshotData(
            file_count=len(files),
            total_bytes=total_bytes,
            newest_mtime=newest_mtime,
            files=files,
        )
