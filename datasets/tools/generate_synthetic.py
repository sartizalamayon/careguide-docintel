"""Deterministic generator for the synthetic, fully-labelled evaluation set.

Why: the public set (Katana ML) only covers clean single-page invoice images. The assessment
also needs digital/scanned PDFs, multi-page and multi-invoice PDFs, TIFF, XLSX (multi-sheet),
XLS, CSV, corrupted files, duplicates, arithmetic errors and PDF<->PDF / PDF<->Excel
cross-verification. Every value printed on a document is recorded as ground truth.

Ground-truth convention: GT = what is PRINTED on the document (the extraction target).
Deliberate errors (wrong totals, missing fields, ...) are listed in `expected_issues`.

Usage:
  python datasets/tools/generate_synthetic.py            # main eval set  (~60 files, committed)
  python datasets/tools/generate_synthetic.py --perf     # only the 1000-page PDF & 50-page scan (gitignored)

Needs: reportlab faker pymupdf pillow numpy opencv-python-headless openpyxl xlwt
"""
from __future__ import annotations

import argparse
import io
import json
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import cv2
import pymupdf as fitz
import numpy as np
import openpyxl
import xlwt
from faker import Faker
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

SEED = 42
ROOT = Path(__file__).resolve().parents[1] / "eval"
OUT = ROOT / "synthetic"
rng = random.Random(SEED)
fake = Faker(["en_US", "en_GB"])
Faker.seed(SEED)
C2 = Decimal("0.01")

BD_COMPANIES = [
    "Rahman Medical Supplies Ltd.", "Dhaka Office Solutions", "Meghna Care Services",
    "Padma Health Logistics", "Banani Tech Ventures Ltd.", "Chittagong Print House",
]
CATALOGUE = [
    ("Caregiver hours - weekday", 18, 32), ("Caregiver hours - weekend", 24, 40),
    ("Medical billing services (monthly)", 400, 1500), ("Nitrile gloves, box of 100", 6, 14),
    ("Wheelchair rental (monthly)", 45, 120), ("Data entry services (hours)", 8, 20),
    ("Cloud hosting - standard plan", 50, 300), ("Office chair, ergonomic", 90, 260),
    ("Blood pressure monitor", 25, 80), ("Printer toner cartridge", 30, 95),
    ("Laptop, 14-inch business", 650, 1400), ("HHA training course seat", 150, 450),
    ("Disinfectant spray 500ml", 3, 9), ("Scheduling software licence (annual)", 300, 1200),
    ("Courier delivery", 5, 40), ("Adult diapers, pack of 20", 12, 28),
]
CURRENCIES = {
    "USD": {"sym": "$", "fmt": "us", "dates": ["%m/%d/%Y", "%B %d, %Y"]},
    "EUR": {"sym": "€", "fmt": "eu", "dates": ["%d.%m.%Y"]},
    "GBP": {"sym": "£", "fmt": "us", "dates": ["%d/%m/%Y", "%d %B %Y"]},
    "BDT": {"sym": "BDT ", "fmt": "us", "dates": ["%d %b %Y", "%d-%m-%Y"]},
}
LBL_NUM = ["Invoice No:", "Invoice #", "Invoice Number:", "Bill No.:"]
LBL_DATE = ["Invoice Date:", "Date:", "Date of issue:", "Issue Date:"]
LBL_CUST = ["Bill To", "Customer", "Billed To", "Client"]
LBL_SUB = ["Subtotal", "Net Amount", "Sub-total"]
LBL_TAX = ["Tax", "VAT", "GST"]
LBL_TOT = ["Total", "Amount Due", "Grand Total", "Total Due"]


def q2(x) -> Decimal:
    return Decimal(x).quantize(C2, rounding=ROUND_HALF_UP)


def fmt_money(v: Decimal, cur: str, sym: bool = True) -> str:
    s = f"{v:,.2f}"
    if CURRENCIES[cur]["fmt"] == "eu":
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return (CURRENCIES[cur]["sym"] + s) if sym else s


@dataclass
class Inv:
    number: str | None
    issued: date
    supplier: str
    supplier_addr: str
    customer: str | None
    customer_addr: str
    currency: str
    items: list[dict]
    tax_rate: Decimal | None
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None
    date_fmt: str = "%Y-%m-%d"
    labels: dict = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    po: str = ""
    due: date | None = None

    def gt(self) -> dict:
        return {
            "invoice_number": self.number,
            "invoice_date": self.issued.isoformat(),
            "supplier_name": self.supplier,
            "customer_name": self.customer,
            "currency": self.currency,
            "subtotal": str(self.subtotal) if self.subtotal is not None else None,
            "tax": str(self.tax) if self.tax is not None else None,
            "total": str(self.total),
            "line_items": [
                {"description": i["description"], "quantity": str(i["quantity"]),
                 "unit_price": str(i["unit_price"]), "amount": str(i["amount"])}
                for i in self.items
            ],
        }


_seq = iter(range(1000, 999999))


def make_invoice(n_items: int | None = None, currency: str | None = None, prefix: str | None = None) -> Inv:
    cur = currency or rng.choice(["USD", "USD", "EUR", "GBP", "BDT"])
    supplier = rng.choice(BD_COMPANIES) if cur == "BDT" else fake.company()
    customer = fake.company() if rng.random() < 0.7 else fake.name()
    issued = date(2025, 1, 1) + timedelta(days=rng.randint(0, 600))
    fmt = rng.choice(CURRENCIES[cur]["dates"])
    if fmt.startswith(("%m/%d", "%d/%m", "%d.%m", "%d-%m")) and issued.day <= 12:
        issued = issued.replace(day=rng.randint(13, 28))  # keep numeric dates unambiguous
    items = []
    for _ in range(n_items or rng.randint(1, 7)):
        desc, lo, hi = rng.choice(CATALOGUE)
        qty = Decimal(rng.choice([1, 1, 2, 3, 4, 5, 8, 10, 12, 20, 40]))
        price = q2(rng.uniform(lo, hi))
        items.append({"description": desc, "quantity": qty, "unit_price": price, "amount": q2(qty * price)})
    rate = Decimal(rng.choice(["0.05", "0.075", "0.10", "0.15", "0.20"]))
    inv = Inv(
        number=f"{prefix or rng.choice(['INV', 'CG', 'BL', 'INV-2025'])}-{next(_seq)}",
        issued=issued, supplier=supplier, supplier_addr=fake.address().replace("\n", ", "),
        customer=customer, customer_addr=fake.address().replace("\n", ", "), currency=cur,
        items=items, tax_rate=rate, date_fmt=fmt, po=f"PO-{rng.randint(10000, 99999)}",
        labels={k: rng.choice(v) for k, v in
                {"num": LBL_NUM, "date": LBL_DATE, "cust": LBL_CUST, "sub": LBL_SUB, "tax": LBL_TAX, "tot": LBL_TOT}.items()},
    )
    inv.due = issued + timedelta(days=rng.choice([14, 30, 45]))
    recompute(inv)
    return inv


def recompute(inv: Inv) -> None:
    inv.subtotal = q2(sum(i["amount"] for i in inv.items))
    inv.tax = q2(inv.subtotal * inv.tax_rate) if inv.tax_rate is not None else None
    inv.total = inv.subtotal + (inv.tax or 0)


# ----------------------------------------------------------------- faults
def fault(inv: Inv, kind: str) -> Inv:
    if kind == "TOTAL_MISMATCH":
        inv.total = inv.total + Decimal("10.00")
    elif kind == "SUBTOTAL_MISMATCH":
        inv.subtotal = inv.subtotal + Decimal("25.00")
        inv.tax = q2(inv.subtotal * inv.tax_rate)
        inv.total = inv.subtotal + inv.tax
    elif kind == "LINE_AMOUNT_MISMATCH":
        inv.items[0]["amount"] = inv.items[0]["amount"] + Decimal("5.00")
        recompute_keep_lines(inv)
    elif kind == "MISSING_FIELD:invoice_number":
        inv.number = None
    elif kind == "MISSING_FIELD:customer_name":
        inv.customer = None
    elif kind == "MISSING_FIELD:tax":
        inv.tax_rate, inv.tax = None, None
        inv.total = inv.subtotal
    elif kind == "INVALID_DATE":
        inv.issued = date(2027, rng.randint(2, 11), rng.randint(13, 28))  # future-dated
        inv.due = inv.issued + timedelta(days=30)
    inv.issues.append(kind)
    return inv


def recompute_keep_lines(inv: Inv) -> None:
    inv.subtotal = q2(sum(i["amount"] for i in inv.items))
    inv.tax = q2(inv.subtotal * inv.tax_rate)
    inv.total = inv.subtotal + inv.tax


# ----------------------------------------------------------------- PDF rendering
W, H = A4


def _wrap(c: canvas.Canvas, text: str, font: str, size: float, width: float) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if c.stringWidth(t, font, size) > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = t
    return lines + [cur] if cur else lines


def draw_invoice(c: canvas.Canvas, inv: Inv, template: str) -> None:
    """Draws one invoice (may span several pages). Leaves the canvas after its last showPage()."""
    L = inv.labels
    per_page_first, per_page_next = 16, 30
    chunks, rest = [inv.items[:per_page_first]], inv.items[per_page_first:]
    while rest:
        chunks.append(rest[:per_page_next])
        rest = rest[per_page_next:]
    pages = len(chunks)
    head_font = {"classic": "Helvetica-Bold", "modern": "Helvetica-Bold", "minimal": "Courier-Bold"}[template]
    body_font = {"classic": "Helvetica", "modern": "Helvetica", "minimal": "Courier"}[template]
    for p, chunk in enumerate(chunks, start=1):
        y = H - 50
        if p == 1:
            if template == "modern":
                c.setFillColor(colors.HexColor("#1C3462"))
                c.rect(0, H - 95, W, 95, fill=1, stroke=0)
                c.setFillColor(colors.white)
                c.setFont(head_font, 20)
                c.drawString(40, H - 50, inv.supplier)
                c.setFont(body_font, 9)
                c.drawString(40, H - 70, inv.supplier_addr[:95])
                c.setFont(head_font, 24)
                c.drawRightString(W - 40, H - 55, "INVOICE")
                c.setFillColor(colors.black)
                y = H - 125
            else:
                c.setFont(head_font, 18 if template == "classic" else 14)
                c.drawString(40, y, inv.supplier)
                c.setFont(body_font, 9)
                c.drawString(40, y - 15, inv.supplier_addr[:95])
                c.setFont(head_font, 22 if template == "classic" else 14)
                c.drawRightString(W - 40, y, "INVOICE" if template == "classic" else "TAX INVOICE")
                y -= 55
            c.setFont(body_font, 10)
            meta = []
            if inv.number:
                meta.append((L["num"], inv.number))
            meta += [(L["date"], inv.issued.strftime(inv.date_fmt)),
                     ("Due Date:", inv.due.strftime(inv.date_fmt)), ("PO Number:", inv.po)]
            for k, v in meta:
                c.drawRightString(W - 150, y, k)
                c.drawString(W - 140, y, v)
                y -= 14
            yb = y + 14 * len(meta)
            c.setFont(head_font, 10)
            c.drawString(40, yb, L["cust"] + ":")
            c.setFont(body_font, 10)
            yy = yb - 14
            if inv.customer:
                c.drawString(40, yy, inv.customer)
                yy -= 13
            for line in _wrap(c, inv.customer_addr, body_font, 9, 230):
                c.setFont(body_font, 9)
                c.drawString(40, yy, line)
                yy -= 12
            y = min(y, yy) - 20
        else:
            c.setFont(body_font, 10)
            c.drawString(40, y, f"{inv.supplier}  -  {L['num']} {inv.number or ''} (continued)")
            y -= 30
        # table
        cols = [40, 65, 330, 380, 470] if template != "minimal" else [40, 60, 320, 370, 460]
        hdr = ["#", "Description", "Qty", "Unit Price", "Amount"] if template != "modern" else ["No", "Item", "Qty", "Rate", "Line Total"]
        c.setFont(head_font, 9)
        if template != "minimal":
            c.setFillColor(colors.HexColor("#E8ECF3"))
            c.rect(36, y - 4, W - 72, 16, fill=1, stroke=0)
            c.setFillColor(colors.black)
        for x, h in zip(cols, hdr):
            (c.drawRightString(x + 75, y, h) if h in ("Unit Price", "Amount", "Rate", "Line Total") else c.drawString(x, y, h))
        y -= 18
        c.setFont(body_font, 9)
        start = 0 if p == 1 else per_page_first + (p - 2) * per_page_next
        for k, it in enumerate(chunk, start=start + 1):
            c.drawString(cols[0], y, f"{k}.")
            c.drawString(cols[1], y, it["description"][:48])
            c.drawString(cols[2], y, f"{it['quantity']}")
            c.drawRightString(cols[3] + 75, y, fmt_money(it["unit_price"], inv.currency, sym=False))
            c.drawRightString(cols[4] + 75, y, fmt_money(it["amount"], inv.currency, sym=False))
            y -= 16
        if p == pages:
            y -= 10
            c.line(330, y + 8, W - 40, y + 8)
            rows = [(L["sub"], inv.subtotal)]
            if inv.tax is not None:
                pct = f"{(inv.tax_rate * 100).normalize():f}%"
                rows.append((f"{L['tax']} ({pct})", inv.tax))
            rows.append((L["tot"], inv.total))
            for i, (k, v) in enumerate(rows):
                c.setFont(head_font if i == len(rows) - 1 else body_font, 10 if i < len(rows) - 1 else 12)
                c.drawRightString(440, y - 4, k)
                c.drawRightString(W - 45, y - 4, fmt_money(v, inv.currency))
                y -= 18
            c.setFont(body_font, 8)
            c.drawString(40, 60, f"Payment terms: due {inv.due.strftime(inv.date_fmt)}. Thank you for your business.")
        c.setFont(body_font, 8)
        c.drawRightString(W - 40, 30, f"Page {p} of {pages}")
        c.showPage()


def pdf_bytes(invoices: list[Inv], templates: list[str] | None = None, encrypt: bool = False) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, invariant=1)
    for i, inv in enumerate(invoices):
        t = templates[i % len(templates)] if templates else rng.choice(["classic", "modern", "minimal"])
        draw_invoice(c, inv, t)
    c.save()
    data = buf.getvalue()
    if encrypt:
        d = fitz.open(stream=data, filetype="pdf")
        data = d.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner")
    return data


# ----------------------------------------------------------------- scan / photo simulation
def rasterize(pdf: bytes, dpi: int = 200) -> list[Image.Image]:
    d = fitz.open(stream=pdf, filetype="pdf")
    return [Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            for pix in (pg.get_pixmap(dpi=dpi) for pg in d)]


def scanify(img: Image.Image, strength: float = 1.0) -> Image.Image:
    a = np.array(img.convert("L")).astype(np.float32)
    h, w = a.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), rng.uniform(-1.8, 1.8) * strength, 1.0)
    a = cv2.warpAffine(a, m, (w, h), borderValue=245)
    a = cv2.GaussianBlur(a, (3, 3), 0.7 * strength)
    a = a * rng.uniform(0.8, 0.92) + rng.uniform(10, 25)
    a += np.random.default_rng(rng.randint(0, 10**6)).normal(0, 6 * strength, a.shape)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def photoify(img: Image.Image) -> Image.Image:
    """Phone-photo look: rotation, uneven lighting, noise, JPEG later."""
    a = np.array(scanify(img, 1.4)).astype(np.float32)
    h, w = a.shape
    grad = np.linspace(0.78, 1.05, w)[None, :] * np.linspace(0.9, 1.0, h)[:, None]
    return Image.fromarray(np.clip(a * grad, 0, 255).astype(np.uint8))


def images_to_pdf(imgs: list[Image.Image]) -> bytes:
    d = fitz.open()
    for im in imgs:
        b = io.BytesIO()
        im.save(b, "JPEG", quality=70)
        pg = d.new_page(width=A4[0], height=A4[1])
        pg.insert_image(pg.rect, stream=b.getvalue())
    return d.tobytes()


# ----------------------------------------------------------------- spreadsheets
REG_COLS = ["Invoice No", "Invoice Date", "Vendor", "Customer", "Currency", "Description",
            "Qty", "Unit Price", "Line Total", "Subtotal", "Tax", "Total"]


def register_rows(inv: Inv) -> list[list]:
    rows = []
    for it in inv.items:
        rows.append([inv.number, inv.issued, inv.supplier, inv.customer, inv.currency, it["description"],
                     float(it["quantity"]), float(it["unit_price"]), float(it["amount"]),
                     float(inv.subtotal), float(inv.tax) if inv.tax is not None else None, float(inv.total)])
    return rows


def write_register_xlsx(path: Path, sheets: dict[str, list[Inv]], notes_sheet: bool = True) -> None:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, invs in sheets.items():
        ws = wb.create_sheet(name)
        ws.append([f"Accounts payable register - {name}"])  # title row above the header (header detection test)
        ws.append([])
        ws.append(REG_COLS)
        for inv in invs:
            for r in register_rows(inv):
                ws.append(r)
                ws.cell(ws.max_row, 2).number_format = "yyyy-mm-dd"
    if notes_sheet:
        ws = wb.create_sheet("Notes")
        ws.append(["Prepared by finance team. Figures exclude bank charges."])
    wb.save(path)


def write_layout_xlsx(path: Path, inv: Inv) -> None:
    """An invoice laid out in cells (template-style), not a table."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Invoice"
    ws["A1"] = inv.supplier
    ws["A2"] = inv.supplier_addr
    ws["E1"] = "INVOICE"
    ws["D3"], ws["E3"] = inv.labels["num"], inv.number
    ws["D4"], ws["E4"] = inv.labels["date"], inv.issued.strftime(inv.date_fmt)
    ws["A6"], ws["A7"] = inv.labels["cust"], inv.customer
    ws.append([])
    ws["A9"], ws["B9"], ws["C9"], ws["D9"], ws["E9"] = "#", "Description", "Qty", "Unit Price", "Amount"
    r = 10
    for k, it in enumerate(inv.items, 1):
        for col, v in zip("ABCDE", [k, it["description"], float(it["quantity"]), float(it["unit_price"]), float(it["amount"])]):
            ws[f"{col}{r}"] = v
        r += 1
    r += 1
    ws[f"D{r}"], ws[f"E{r}"] = inv.labels["sub"], float(inv.subtotal)
    ws[f"D{r + 1}"], ws[f"E{r + 1}"] = f"{inv.labels['tax']} ({(inv.tax_rate * 100).normalize():f}%)", float(inv.tax)
    ws[f"D{r + 2}"], ws[f"E{r + 2}"] = inv.labels["tot"], float(inv.total)
    ws[f"A{r + 4}"] = f"Currency: {inv.currency}"
    wb.save(path)


def write_ledger_xls(path: Path, invs: list[Inv]) -> None:
    """Header-level ledger (one row per invoice), legacy .xls, different column names."""
    wb = xlwt.Workbook()
    ws = wb.add_sheet("Ledger")
    hdr = ["Bill No", "Bill Date", "Supplier", "Client", "Curr", "Net", "VAT", "Gross"]
    for j, h in enumerate(hdr):
        ws.write(0, j, h)
    for i, inv in enumerate(invs, 1):
        vals = [inv.number, inv.issued.strftime("%d/%m/%Y"), inv.supplier, inv.customer, inv.currency,
                float(inv.subtotal), float(inv.tax), float(inv.total)]
        for j, v in enumerate(vals):
            ws.write(i, j, v)
    wb.save(str(path))


def write_export_csv(path: Path, invs: list[Inv], bad_number_inv: Inv | None) -> None:
    """Semicolon-delimited, comma decimals, UTF-8 BOM (typical EU ERP export)."""
    def eu(v):
        return "" if v is None else f"{v:.2f}".replace(".", ",")
    lines = ["invoice_number;date;supplier;customer;currency;item;quantity;price;line_amount;net_total;vat_total;gross_total"]
    for inv in invs:
        for it in inv.items:
            gross = eu(inv.total)
            if inv is bad_number_inv:
                gross = gross.replace("0", "O", 1) if "0" in gross else "N/A"  # data-entry typo
            lines.append(";".join([inv.number, inv.issued.isoformat(), inv.supplier, inv.customer or "", inv.currency,
                                   it["description"], str(it["quantity"]), eu(it["unit_price"]), eu(it["amount"]),
                                   eu(inv.subtotal), eu(inv.tax), gross]))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


# ----------------------------------------------------------------- manifest helpers
MANIFEST: list[dict] = []


def add(path: Path, file_type: str, category: str, invs: list[Inv] | None, outcome: str = "success",
        error: str | None = None, gt_override: list[dict] | None = None, **extra) -> str:
    doc_id = "syn-" + path.stem
    MANIFEST.append({
        "doc_id": doc_id, "path": str(path.relative_to(ROOT)), "source": "synthetic", "file_type": file_type,
        "category": category, "expected_outcome": outcome, "expected_error": error,
        "invoices": gt_override if gt_override is not None else [i.gt() for i in (invs or [])],
        "expected_issues": [{"invoice_number": i.number, "code": c.split(":")[0],
                             "field": c.split(":")[1] if ":" in c else None}
                            for i in (invs or []) for c in i.issues],
        "eval_hints": {}, **extra,
    })
    return doc_id


def w(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


# ----------------------------------------------------------------- main set
def build_main() -> None:
    xchecks, dup_groups = [], []
    tpl = ["classic", "modern", "minimal"]

    # 1) digital PDFs: 20 single-page + 4 multi-page
    faults = {2: "TOTAL_MISMATCH", 5: "SUBTOTAL_MISMATCH", 8: "MISSING_FIELD:invoice_number",
              11: "MISSING_FIELD:customer_name", 14: "MISSING_FIELD:tax", 17: "INVALID_DATE"}
    digital = []
    for i in range(20):
        inv = make_invoice()
        if i in faults:
            fault(inv, faults[i])
        p = w(OUT / "digital_pdf" / f"digital_{i:02d}.pdf", pdf_bytes([inv], [tpl[i % 3]]))
        digital.append((add(p, "pdf", "digital_pdf", [inv]), inv, i))
    for i in range(4):
        inv = make_invoice(n_items=rng.randint(22, 60))
        p = w(OUT / "digital_pdf" / f"multipage_{i:02d}.pdf", pdf_bytes([inv], [tpl[i % 3]]))
        add(p, "pdf", "digital_pdf_multipage", [inv])

    # 2) scanned PDFs (image-only): 8, one has a wrong total, one duplicates digital_03
    for i in range(8):
        if i == 0:
            src = digital[3][1]
            inv = src
        else:
            inv = make_invoice(n_items=rng.randint(1, 30) if i == 7 else None)
            if i == 4:
                fault(inv, "TOTAL_MISMATCH")
        imgs = [scanify(im) for im in rasterize(pdf_bytes([inv], [tpl[i % 3]]))]
        p = w(OUT / "scanned_pdf" / f"scanned_{i:02d}.pdf", images_to_pdf(imgs))
        did = add(p, "pdf", "scanned_pdf", [inv], gt_override=[inv.gt()])
        if i == 0:
            MANIFEST[-1]["expected_issues"] = []  # duplicate is evaluated via duplicate_groups
            dup_groups.append([digital[3][0], did])

    # 3) images: 4 png (clean), 4 jpg (phone photo), 3 tiff (one multi-page)
    for i in range(4):
        inv = make_invoice()
        if i == 1:
            fault(inv, "LINE_AMOUNT_MISMATCH")
        im = rasterize(pdf_bytes([inv], [tpl[i % 3]]), dpi=200)[0]
        p = OUT / "images" / f"clean_{i:02d}.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        im.save(p, optimize=True)
        add(p, "png", "image_clean", [inv])
    for i in range(4):
        if i == 3:  # re-billed duplicate of digital_07: same number & supplier, new date
            inv = make_invoice()
            src = digital[7][1]
            inv.number, inv.supplier, inv.supplier_addr = src.number, src.supplier, src.supplier_addr
        else:
            inv = make_invoice()
        im = photoify(rasterize(pdf_bytes([inv], [tpl[i % 3]]), dpi=170)[0])
        p = OUT / "images" / f"photo_{i:02d}.jpg"
        im.save(p, quality=72)
        did = add(p, "jpg", "image_photo", [inv])
        if i == 3:
            dup_groups.append([digital[7][0], did])
    for i in range(3):
        inv = make_invoice(n_items=rng.randint(20, 26) if i == 2 else None)
        pages = [scanify(im, 0.8) for im in rasterize(pdf_bytes([inv], [tpl[i % 3]]), dpi=200)]
        p = OUT / "images" / f"scan_{i:02d}.tiff"
        pages[0].save(p, save_all=True, append_images=pages[1:], compression="tiff_adobe_deflate")
        add(p, "tiff", "image_tiff_multipage" if len(pages) > 1 else "image_tiff", [inv], pages=len(pages))

    # 4) spreadsheets
    q1, q2_ = [make_invoice() for _ in range(5)], [make_invoice() for _ in range(5)]
    p = OUT / "spreadsheets" / "ap_register_2025.xlsx"
    p.parent.mkdir(parents=True, exist_ok=True)
    write_register_xlsx(p, {"Q1": q1, "Q2": q2_})
    add(p, "xlsx", "xlsx_multisheet_register", q1 + q2_)

    ledger = [make_invoice(currency="BDT") for _ in range(6)]
    p = OUT / "spreadsheets" / "supplier_ledger.xls"
    write_ledger_xls(p, ledger)
    gt = []
    for inv in ledger:  # header-level only: no line items in this file
        g = inv.gt()
        g["line_items"] = []
        gt.append(g)
    add(p, "xls", "xls_ledger", ledger, gt_override=gt)

    exp = [make_invoice(currency="EUR") for _ in range(6)]
    bad = exp[4]
    p = OUT / "spreadsheets" / "erp_export_eu.csv"
    write_export_csv(p, exp, bad_number_inv=bad)
    gt = [i.gt() for i in exp]
    for g in gt:
        if g["invoice_number"] == bad.number:
            g["total"] = None  # unreadable number in the source -> must stay null
    add(p, "csv", "csv_semicolon_eu", exp, gt_override=gt)
    MANIFEST[-1]["expected_issues"].append({"invoice_number": bad.number, "code": "INVALID_NUMBER", "field": "total"})

    for i in range(2):
        inv = make_invoice()
        p = OUT / "spreadsheets" / f"invoice_layout_{i:02d}.xlsx"
        write_layout_xlsx(p, inv)
        add(p, "xlsx", "xlsx_invoice_layout", [inv])

    # 5) cross-verification sets
    batch = [make_invoice(prefix="AP") for _ in range(5)]
    p = w(OUT / "crosscheck" / "batch_5_invoices.pdf", pdf_bytes(batch, tpl))
    a = add(p, "pdf", "pdf_multi_invoice", batch)
    erp = []
    for k, inv in enumerate(batch[:4]):
        e = Inv(**{**inv.__dict__, "items": [dict(x) for x in inv.items], "issues": []})
        if k == 1:
            e.total = e.total + Decimal("100.00")
            e.issues.append("TOTAL_MISMATCH")  # register row no longer adds up either
        if k == 2:
            e.issued = e.issued + timedelta(days=3)
        erp.append(e)
    extra = make_invoice(prefix="AP")
    erp.append(extra)
    p = OUT / "crosscheck" / "erp_export.xlsx"
    write_register_xlsx(p, {"Invoices": erp}, notes_sheet=False)
    b = add(p, "xlsx", "xlsx_register", erp)
    xchecks.append({"a": a, "b": b, "kind": "pdf_excel", "expected": {
        "matched": [batch[0].number, batch[3].number],
        "mismatched": [{"invoice_number": batch[1].number, "fields": ["total"]},
                       {"invoice_number": batch[2].number, "fields": ["invoice_date"]}],
        "only_in_a": [batch[4].number], "only_in_b": [extra.number]}})

    pair = [make_invoice(prefix="SUP") for _ in range(2)]
    p = w(OUT / "crosscheck" / "pdfpair_original.pdf", pdf_bytes(pair, ["classic", "modern"]))
    a = add(p, "pdf", "pdf_multi_invoice", pair)
    recv = [Inv(**{**x.__dict__, "items": [dict(y) for y in x.items], "issues": []}) for x in pair]
    recv[1].tax = recv[1].tax + Decimal("3.00")
    recv[1].issues.append("TOTAL_MISMATCH")  # subtotal + tax no longer equals total
    imgs = [scanify(im) for im in rasterize(pdf_bytes(recv, ["classic", "modern"]))]
    p = w(OUT / "crosscheck" / "pdfpair_received_scan.pdf", images_to_pdf(imgs))
    b = add(p, "pdf", "scanned_pdf_multi_invoice", recv)
    xchecks.append({"a": a, "b": b, "kind": "pdf_pdf", "expected": {
        "matched": [pair[0].number], "mismatched": [{"invoice_number": pair[1].number, "fields": ["tax"]}],
        "only_in_a": [], "only_in_b": []}})
    dup_groups += [[a, b]]

    # 6) corrupted / invalid files
    c = OUT / "corrupted"
    good = pdf_bytes([make_invoice()])
    add(w(c / "zero_bytes.pdf", b""), "pdf", "corrupted", None, "rejected", "EMPTY_FILE")
    add(w(c / "not_really_a.pdf", b"Hello, this is a plain text file pretending to be a PDF.\n" * 20),
        "pdf", "corrupted", None, "rejected", "FILE_TYPE_MISMATCH")
    add(w(c / "unsupported.docx", b"PK\x03\x04" + bytes(rng.getrandbits(8) for _ in range(800))),
        "docx", "corrupted", None, "rejected", "UNSUPPORTED_FILE_TYPE")
    broken = b"%PDF-1.7\n" + bytes(rng.getrandbits(8) for _ in range(4000))
    add(w(c / "broken_body.pdf", broken), "pdf", "corrupted", None, "failed", "CORRUPTED_FILE")
    add(w(c / "password_protected.pdf", pdf_bytes([make_invoice()], encrypt=True)),
        "pdf", "corrupted", None, "failed", "ENCRYPTED_FILE")
    add(w(c / "corrupt_workbook.xlsx", b"PK\x03\x04" + good[100:3000]), "xlsx", "corrupted", None, "failed", "CORRUPTED_FILE")
    blank = Image.new("RGB", (1654, 2339), "white")
    blank.save(c / "blank_page.png")
    add(c / "blank_page.png", "png", "corrupted", None, "failed", "NO_CONTENT")
    (c / "header_only.csv").write_text("invoice_number,date,supplier,total\n")
    add(c / "header_only.csv", "csv", "corrupted", None, "failed", "NO_CONTENT")

    # sanity: the "failed" PDFs really are unreadable
    for name in ("broken_body.pdf",):
        try:
            fitz.open(c / name)
            raise SystemExit(f"{name} unexpectedly opens")
        except fitz.FileDataError:
            pass
    assert fitz.open(c / "password_protected.pdf").needs_pass

    with open(ROOT / "manifest_synthetic.jsonl", "w") as f:
        for r in MANIFEST:
            f.write(json.dumps(r, default=str) + "\n")
    meta = {"duplicate_groups": dup_groups, "crosschecks": xchecks}
    (ROOT / "synthetic_meta.json").write_text(json.dumps(meta, indent=2))
    n_inv = sum(len(r["invoices"]) for r in MANIFEST)
    print(f"synthetic: {len(MANIFEST)} files, {n_inv} invoices -> {ROOT}")


# ----------------------------------------------------------------- performance set
def build_perf() -> None:
    perf = ROOT / "perf"
    perf.mkdir(parents=True, exist_ok=True)
    invs, pages = [], 0
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, invariant=1)
    tpl = ["classic", "modern", "minimal"]
    while pages < 1000:
        n_pages = rng.choice([1, 1, 1, 2, 2, 3, 4])
        n_pages = min(n_pages, 1000 - pages)
        n_items = rng.randint(1, 14) if n_pages == 1 else 16 + 30 * (n_pages - 2) + rng.randint(1, 30)
        inv = make_invoice(n_items=n_items, prefix="PERF")
        draw_invoice(c, inv, tpl[len(invs) % 3])
        invs.append(inv)
        pages += n_pages
    c.save()
    (perf / "perf_1000_pages.pdf").write_bytes(buf.getvalue())
    n = fitz.open(perf / "perf_1000_pages.pdf").page_count
    with open(ROOT / "manifest_perf.jsonl", "w") as f:
        f.write(json.dumps({"doc_id": "perf-1000", "path": "perf/perf_1000_pages.pdf", "source": "synthetic",
                            "file_type": "pdf", "category": "perf_digital_1000", "pages": n,
                            "expected_outcome": "success", "expected_error": None,
                            "invoices": [i.gt() for i in invs], "expected_issues": [], "eval_hints": {}}) + "\n")
        sub = [make_invoice(prefix="SCAN") for _ in range(50)]
        imgs = [scanify(im) for im in rasterize(pdf_bytes(sub, tpl), dpi=200)]
        (perf / "perf_scanned_50_pages.pdf").write_bytes(images_to_pdf(imgs))
        f.write(json.dumps({"doc_id": "perf-scan-50", "path": "perf/perf_scanned_50_pages.pdf", "source": "synthetic",
                            "file_type": "pdf", "category": "perf_scanned_50", "pages": len(imgs),
                            "expected_outcome": "success", "expected_error": None,
                            "invoices": [i.gt() for i in sub], "expected_issues": [], "eval_hints": {}}) + "\n")
    print(f"perf: {n} pages / {len(invs)} invoices, scanned {len(imgs)} pages")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--perf", action="store_true", help="also build the 1000-page performance PDFs")
    args = ap.parse_args()
    if args.perf:
        build_perf()
    else:
        build_main()
