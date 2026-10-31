"""Amount, date and name helpers shared by extraction, validation, search and cross-checks (SPEC §5, §6.5, §6.8)."""
from __future__ import annotations

import datetime as dt
import math
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")
LEGAL_SUFFIXES = {"ltd", "limited", "llc", "inc", "plc", "gmbh", "co", "corp", "corporation", "company"}

_CURRENCY_TOKENS = re.compile(r"(?i)\b(usd|eur|gbp|bdt|inr|tk|taka|rs)\b|[$€£৳₹]")
_NUMBER = re.compile(r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?")

DATE_PATTERNS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d.%m.%Y",
    "%d-%m-%Y",
    "%d %B %Y",
    "%d %b %Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d/%m/%y",
    "%m/%d/%y",
)


def to_cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def parse_amount(raw: object) -> Decimal | None:
    """Parse a printed amount: '$ 1 234,56' -> 1234.56, '1.234,56' -> 1234.56, '(50.00)' -> -50.00.

    Returns None when the text is not a number ('12O.50'). Never guesses.
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int | Decimal):
        return Decimal(raw)
    if isinstance(raw, float):
        return None if not math.isfinite(raw) else Decimal(str(raw))

    text = str(raw).strip().replace(" ", " ")
    if not text:
        return None
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()
    text = _CURRENCY_TOKENS.sub("", text).strip()
    if text.startswith("-") or text.endswith("-"):
        negative = True
        text = text.strip("-").strip()
    text = text.replace(" ", "").strip()
    if not _NUMBER.fullmatch(text):
        return None

    last_sep = max(text.rfind("."), text.rfind(","))
    if last_sep >= 0:
        sep = text[last_sep]
        digits_after = len(text) - last_sep - 1
        other = "," if sep == "." else "."
        if other in text:
            decimal_sep = sep  # both kinds present: the last one is the decimal separator
        elif text.count(sep) > 1:
            decimal_sep = None  # repeated separator -> thousands
        elif digits_after == 3:
            decimal_sep = None  # '1,234' or '1.234' -> thousands
        else:
            decimal_sep = sep
    else:
        decimal_sep = None

    integer, fraction = text, ""
    if decimal_sep is not None:
        integer, fraction = text.rsplit(decimal_sep, 1)
    integer = re.sub(r"[.,]", "", integer)
    try:
        value = Decimal(f"{integer}.{fraction}" if fraction else integer)
    except InvalidOperation:
        return None
    return -value if negative else value


def norm_invoice_number(value: str | None) -> str | None:
    """Upper case, letters and digits only. Empty -> None (SPEC §5)."""
    if value is None:
        return None
    cleaned = re.sub(r"[^A-Z0-9]", "", value.upper())
    return cleaned or None


def norm_supplier(value: str | None) -> str | None:
    """Lower case, '&' -> 'and', punctuation removed, trailing legal suffixes removed (SPEC §5)."""
    if value is None:
        return None
    text = value.lower().replace("&", " and ")
    text = re.sub(r"[^\w\s]", " ", text).replace("_", " ")
    words = text.split()
    while words and words[-1] in LEGAL_SUFFIXES:
        words.pop()
    result = " ".join(words)
    return result or None


def parse_date(value: object) -> dt.date | None:
    """Parse a printed date. Accepts ISO and the day-first and month-first patterns of SPEC §6.8.

    For ambiguous numeric dates (both parts <= 12) day-first is used. Callers that know the locale should
    pass a datetime/date instead.
    """
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for pattern in DATE_PATTERNS:
        try:
            return dt.datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def amount_variants(value: Decimal | float | int | str) -> set[str]:
    """Ways a number can be printed, used by the grounding check (SPEC §6.8)."""
    amount = to_cents(Decimal(str(value)))
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    whole, cents = f"{amount:.2f}".split(".")
    grouped = f"{int(whole):,}"
    variants = {
        f"{grouped}.{cents}",
        f"{whole}.{cents}",
        f"{grouped.replace(',', '.')},{cents}",
        f"{whole},{cents}",
        f"{grouped.replace(',', ' ')},{cents}",
        f"{grouped.replace(',', ' ')}.{cents}",
    }
    if cents == "00":
        variants.update({grouped, whole})
    return {sign + v for v in variants}


def date_variants(value: dt.date) -> set[str]:
    """Lower-case printed forms of a date, padded and unpadded (SPEC §6.8)."""
    out: set[str] = set()
    for pattern in DATE_PATTERNS:
        out.add(value.strftime(pattern).lower())
        unpadded = pattern.replace("%d", str(value.day)).replace("%m", str(value.month))
        out.add(value.strftime(unpadded).lower())
    return out
