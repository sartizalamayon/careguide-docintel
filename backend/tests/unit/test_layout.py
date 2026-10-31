"""U2-U3: column-preserving layout text (SPEC §6.3)."""

from app.pipeline.layout import Word, render


def test_u2_words_far_apart_on_one_line_keep_the_gap():
    words = [Word(0, 100, 36, 112, "Seller"), Word(300, 100, 336, 112, "Client")]

    out = render(words)

    assert "\n" not in out
    assert out.startswith("Seller") and out.endswith("Client")
    gap = out.index("Client") - len("Seller")
    assert gap >= 30
    assert out[len("Seller") : out.index("Client")].strip() == ""


def test_u3_small_y_jitter_groups_into_one_line_and_a_big_gap_starts_a_new_line():
    words = [
        Word(0, 100, 30, 112, "Invoice"),
        Word(40, 102, 60, 114, "No:"),
        Word(70, 98, 110, 110, "INV-1"),
        Word(0, 140, 30, 152, "Total"),
    ]

    lines = render(words).splitlines()

    assert len(lines) == 2
    assert lines[0].split() == ["Invoice", "No:", "INV-1"]
    assert lines[1].strip() == "Total"


def test_words_in_a_line_are_ordered_left_to_right():
    words = [Word(200, 0, 230, 10, "right"), Word(0, 0, 24, 10, "left")]

    assert render(words).split() == ["left", "right"]


def test_common_left_indent_is_stripped():
    words = [Word(120, 0, 150, 10, "alpha"), Word(150, 40, 180, 50, "beta")]

    lines = render(words).splitlines()

    assert lines[0] == "alpha"
    assert lines[1].lstrip() == "beta" and lines[1].startswith(" ")


def test_empty_input_renders_empty_text():
    assert render([]) == ""
