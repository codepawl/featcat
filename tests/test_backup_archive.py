"""Tests for tar.gz pack/unpack with path-traversal guard."""

from __future__ import annotations

import tarfile
from io import BytesIO
from typing import TYPE_CHECKING

import pytest

from featcat.backup.archive import ArchiveError, pack_archive, unpack_archive

if TYPE_CHECKING:
    from pathlib import Path


def test_pack_unpack_round_trip(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("hello", encoding="utf-8")
    (src / "sub").mkdir()
    (src / "sub" / "b.txt").write_text("world", encoding="utf-8")

    archive = tmp_path / "backup.tar.gz"
    pack_archive(src, archive)
    assert archive.exists()

    dst = tmp_path / "dst"
    dst.mkdir()
    out = unpack_archive(archive, dst)
    assert out.is_dir()
    assert (out / "a.txt").read_text(encoding="utf-8") == "hello"
    assert (out / "sub" / "b.txt").read_text(encoding="utf-8") == "world"


def test_pack_refuses_missing_source(tmp_path: Path) -> None:
    archive = tmp_path / "x.tar.gz"
    with pytest.raises(ArchiveError):
        pack_archive(tmp_path / "does_not_exist", archive)


def test_unpack_rejects_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "evil.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        info = tarfile.TarInfo(name="../escaped.txt")
        data = b"oops"
        info.size = len(data)
        tf.addfile(info, BytesIO(data))

    dst = tmp_path / "dst"
    dst.mkdir()
    with pytest.raises(ArchiveError):
        unpack_archive(archive, dst)


def test_unpack_rejects_multi_top_level(tmp_path: Path) -> None:
    archive = tmp_path / "multi.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        for name in ("a/file.txt", "b/file.txt"):
            data = b"x"
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tf.addfile(info, BytesIO(data))

    dst = tmp_path / "dst"
    dst.mkdir()
    with pytest.raises(ArchiveError):
        unpack_archive(archive, dst)


def test_unpack_corrupt_archive(tmp_path: Path) -> None:
    bad = tmp_path / "bad.tar.gz"
    bad.write_bytes(b"not a tarball")
    with pytest.raises(ArchiveError):
        unpack_archive(bad, tmp_path / "out")
