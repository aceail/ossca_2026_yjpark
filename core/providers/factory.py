"""Provider factory — NAEIL_MODE 환경변수로 분기."""

from __future__ import annotations

import os

from .folder import FolderProvider, LocalFolderProvider


def _mode() -> str:
    return (os.environ.get("NAEIL_MODE") or "local").lower()


def get_folder_provider() -> FolderProvider:
    mode = _mode()
    if mode == "local":
        return LocalFolderProvider()
    if mode == "cloud":
        # Wave 5: RemoteAgentFolderProvider — desktop agent가 push한 데이터를
        # DB에서 읽기만 한다. scan 루프는 no-op이 됨.
        from .folder import LocalFolderProvider as _Placeholder  # 임시
        return _Placeholder()
    raise ValueError(f"Unknown NAEIL_MODE: {mode}")
