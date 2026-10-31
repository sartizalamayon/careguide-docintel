"""Streaming upload storage: hash while writing, server-generated paths only (SPEC §6.1, §12)."""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from app.config import get_settings
from app.pipeline.filetypes import canonical_ext

CHUNK = 1024 * 1024
HEAD_BYTES = 4096


class FileTooLargeError(Exception):
    """The upload is larger than MAX_FILE_MB."""


@dataclass
class StreamedFile:
    path: Path
    sha256: str
    size: int
    head: bytes


def upload_root() -> Path:
    root = Path(get_settings().STORAGE_DIR)
    (root / "tmp").mkdir(parents=True, exist_ok=True)
    return root


def stream_to_temp(src: BinaryIO, max_bytes: int) -> StreamedFile:
    """Copy the upload to a temp file in 1 MB chunks, hashing it and counting bytes.

    Raises FileTooLargeError as soon as the limit is passed (the temp file is removed).
    """
    fd, name = tempfile.mkstemp(dir=upload_root() / "tmp", suffix=".part")
    digest = hashlib.sha256()
    size = 0
    head = b""
    try:
        with os.fdopen(fd, "wb") as out:
            while True:
                chunk = src.read(CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise FileTooLargeError()
                if len(head) < HEAD_BYTES:
                    head = (head + chunk)[:HEAD_BYTES]
                digest.update(chunk)
                out.write(chunk)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise
    return StreamedFile(path=Path(name), sha256=digest.hexdigest(), size=size, head=head)


def final_path(document_id: uuid.UUID, file_type: str, now: dt.datetime | None = None) -> Path:
    """{STORAGE_DIR}/{yyyy}/{mm}/{document_id}.{ext}. The name never comes from the upload."""
    when = now or dt.datetime.now(dt.UTC)
    folder = upload_root() / f"{when:%Y}" / f"{when:%m}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{document_id}{canonical_ext(file_type)}"


def move_into_storage(tmp: StreamedFile, document_id: uuid.UUID, file_type: str) -> Path:
    target = final_path(document_id, file_type)
    os.replace(tmp.path, target)
    return target


def discard(tmp: StreamedFile) -> None:
    tmp.path.unlink(missing_ok=True)


def open_path(storage_path: str) -> Path:
    """Path of the stored original. The DB stores the full path, so it can be opened directly."""
    return Path(storage_path)
