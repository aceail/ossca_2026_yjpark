"""Provider abstraction for Local vs Cloud deployment modes.

Local mode (default): backend has direct OS access — file scans, ICS files, etc.
Cloud mode: backend cannot touch user files; a desktop agent pushes snapshots.

Same router code on both ends — only the provider instance changes.
"""

from .folder import FolderProvider, LocalFolderProvider, FolderSnapshotData
from .factory import get_folder_provider

__all__ = [
    "FolderProvider",
    "LocalFolderProvider",
    "FolderSnapshotData",
    "get_folder_provider",
]
