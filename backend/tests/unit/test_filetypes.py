"""U1: file type detection and magic-byte checks (SPEC §6.1)."""

import pytest

from app.pipeline.filetypes import file_type_for, sanitize_filename, sniff

PNG_HEAD = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.mark.parametrize(
    ("filename", "head", "expected"),
    [
        ("invoice.pdf", b"%PDF-1.7\n%....", "pdf"),
        ("scan.PNG", PNG_HEAD, "png"),
        ("photo.jpeg", b"\xff\xd8\xff\xe0\x00\x10JFIF", "jpg"),
        ("multi.tif", b"II*\x00\x08\x00\x00\x00", "tiff"),
        ("book.xlsx", b"PK\x03\x04\x14\x00", "xlsx"),
        ("old.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00", "xls"),
        ("rows.csv", b"Invoice,Total\nAP-1,10.00\n", "csv"),
    ],
)
def test_allowed_types_with_matching_magic_pass(filename, head, expected):
    file_type = file_type_for(filename)
    assert file_type == expected
    assert sniff(head, file_type)


def test_pdf_extension_with_png_bytes_is_a_mismatch():
    assert not sniff(PNG_HEAD, file_type_for("fake.pdf"))


def test_docx_is_not_an_allowed_type():
    assert file_type_for("contract.docx") is None


def test_csv_with_nul_byte_is_a_mismatch():
    assert not sniff(b"Invoice,Total\n\x00\x00\x00", "csv")


def test_csv_with_binary_garbage_is_a_mismatch():
    assert not sniff(bytes(range(128, 256)) * 4 + b"\x00", "csv")


def test_sanitize_filename_strips_paths_and_unsafe_characters():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("C:\\Users\\me\\Inv #1 (final).pdf") == "Inv _1 _final_.pdf"
    assert len(sanitize_filename("a" * 300 + ".pdf")) == 150
    assert sanitize_filename("???") == "upload"
