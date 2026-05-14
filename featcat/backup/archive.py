"""tar.gz pack/unpack with a path-traversal guard.

Defends against the CVE-2007-4559 class — archive members whose relative
path resolves outside the destination are refused, so a malicious backup
file can't write to system locations on unpack.
"""

from __future__ import annotations

import tarfile
from pathlib import Path


class ArchiveError(Exception):
    """Archive could not be packed or unpacked safely."""


def pack_archive(src_dir: Path, archive_path: Path) -> None:
    """Pack ``src_dir`` into ``archive_path`` (tar.gz).

    The archive's single top-level directory matches ``src_dir.name`` so
    unpacking is tidy: one folder shows up in the destination.
    """
    if not src_dir.is_dir():
        raise ArchiveError(f"Source directory not found: {src_dir}")
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "w:gz") as tf:
        tf.add(src_dir, arcname=src_dir.name)


def unpack_archive(archive_path: Path, dest_dir: Path) -> Path:
    """Unpack ``archive_path`` into ``dest_dir``.

    Returns the top-level directory inside ``dest_dir`` produced by the
    archive. Raises ``ArchiveError`` if the archive has multiple top-level
    entries, contains a path-traversal entry, or is corrupt.
    """
    dest_dir = dest_dir.resolve()
    try:
        with tarfile.open(archive_path, "r:gz") as tf:
            members = tf.getmembers()
            top_levels = {Path(m.name).parts[0] for m in members if m.name}
            if len(top_levels) != 1:
                raise ArchiveError(f"Archive must have a single top-level dir, found: {sorted(top_levels)}")
            top = top_levels.pop()
            for m in members:
                target = (dest_dir / m.name).resolve()
                if not _is_within(target, dest_dir):
                    raise ArchiveError(f"Refusing path traversal: {m.name}")
            tf.extractall(dest_dir)
        return dest_dir / top
    except tarfile.TarError as e:
        raise ArchiveError(f"Corrupt archive: {e}") from e


def _is_within(child: Path, parent: Path) -> bool:
    """Return True if ``child`` is the same as or nested inside ``parent``."""
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True
