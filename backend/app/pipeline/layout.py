"""Column-preserving text layout for PDF words and OCR words (SPEC §6.3)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median

LINE_TOLERANCE = 0.5  # new line when the y-centre moves more than this many median word heights


@dataclass(frozen=True)
class Word:
    """A word box. Coordinates in any unit (points or pixels), origin top-left."""

    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def y_centre(self) -> float:
        return (self.y0 + self.y1) / 2


def render(words: Sequence[Word]) -> str:
    """Render word boxes as text that keeps side-by-side columns apart."""
    if not words:
        return ""
    cw = median((w.x1 - w.x0) / max(len(w.text), 1) for w in words) or 1.0
    out = [_render_line(line, cw) for line in group_lines(words)]
    return dedent_and_squeeze(out)


def group_lines(words: Sequence[Word]) -> list[list[Word]]:
    """Group words into lines, top to bottom, by their y-centre."""
    tolerance = LINE_TOLERANCE * median(w.y1 - w.y0 for w in words)
    lines: list[list[Word]] = []
    mean_y = 0.0
    for word in sorted(words, key=lambda w: w.y_centre):
        if lines and abs(word.y_centre - mean_y) <= tolerance:
            lines[-1].append(word)
            mean_y += (word.y_centre - mean_y) / len(lines[-1])
        else:
            lines.append([word])
            mean_y = word.y_centre
    return lines


def _render_line(line: list[Word], cw: float) -> str:
    s = ""
    for word in sorted(line, key=lambda w: w.x0):
        col = int(word.x0 / cw)
        s += " " * (col - len(s)) if len(s) < col else (" " if s else "")
        s += word.text
    return s.rstrip()


def dedent_and_squeeze(lines: list[str]) -> str:
    """Collapse 3+ consecutive blank lines into one and strip the common left indent."""
    return _dedent(_collapse_blank_runs(lines))


def _collapse_blank_runs(lines: list[str]) -> list[str]:
    out: list[str] = []
    run: list[str] = []
    for line in lines:
        if not line.strip():
            run.append("")
            continue
        out.extend(run if len(run) < 3 else [""])
        run = []
        out.append(line)
    out.extend(run if len(run) < 3 else [""])
    return out


def _dedent(lines: list[str]) -> str:
    indents = [len(line) - len(line.lstrip(" ")) for line in lines if line.strip()]
    cut = min(indents, default=0)
    return "\n".join(line[cut:] for line in lines).strip("\n")
