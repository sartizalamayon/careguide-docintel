"""File type detection and magic-byte checks (SPEC §6.1)."""

from __future__ import annotations

import os
import re

import charset_normalizer

EXTENSIONS: dict[str, str] = {
    ".pdf": "pdf",
    ".png": "png",
    ".jpg": "jpg",
    ".jpeg": "jpg",
    ".tif": "tiff",
    ".tiff": "tiff",
    ".xlsx": "xlsx",
    ".xls": "xls",
    ".csv": "csv",
}

FAMILY: dict[str, str] = {
    "pdf": "document",
    "png": "document",
    "jpg": "document",
    "tiff": "document",
    "xlsx": "spreadsheet",
    "xls": "spreadsheet",
    "csv": "spreadsheet",
}

MIME: dict[str, str] = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "tiff": "image/tiff",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "csv": "text/csv",
}

_MAGIC: dict[str, tuple[bytes, ...]] = {
    "pdf": (b"%PDF-",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "tiff": (b"II*\x00", b"MM\x00*"),
    "xlsx": (b"PK\x03\x04",),
    "xls": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
}

_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]")


def file_type_for(filename: str) -> str | None:
    """Return the canonical file type for a filename, or None when the extension is not allowed."""
    return EXTENSIONS.get(os.path.splitext(filename)[1].lower())


def family_of(file_type: str) -> str:
    return FAMILY[file_type]


def mime_of(file_type: str) -> str:
    return MIME[file_type]


def canonical_ext(file_type: str) -> str:
    return f".{file_type}"


def sniff(head: bytes, file_type: str) -> bool:
    """True when the first bytes of the file agree with the file type.

    `head` is the first 4 KB of the file (CSV needs more than a magic number).
    """
    if file_type == "csv":
        if b"\x00" in head:
            return False
        if not head.strip():
            return False
        try:
            head.decode("utf-8-sig")
            return True
        except UnicodeDecodeError:
            return charset_normalizer.from_bytes(head).best() is not None
    return any(head.startswith(magic) for magic in _MAGIC[file_type])


def sanitize_filename(name: str) -> str:
    """Display name: no path parts, only [A-Za-z0-9._ -], at most 150 characters."""
    base = os.path.basename(name.replace("\\", "/"))
    cleaned = _UNSAFE_NAME.sub("_", base).strip(" .")
    if not any(ch.isalnum() for ch in cleaned):
        return "upload"
    return cleaned[:150]
