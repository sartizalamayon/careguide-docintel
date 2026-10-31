"""Download the public labelled invoice set (Katana ML "Sparrow" invoices) and convert
its ground truth to this project's schema.

Source : https://huggingface.co/datasets/katanaml-org/invoices-donut-data-v1  (MIT)
Origin : Kozlowski & Weichbroth (2021), "Samples of electronic invoices", Mendeley Data,
         doi:10.17632/tnj49gpmtz.2
Pinned : revision d2cde298e79c94fb05bc320999deb4b7889b0464

Writes
  datasets/eval/katanaml/<split>_<nn>.jpg          original scans (300 dpi JPEG)
  datasets/eval/katanaml/degraded/<...>.png|tiff   poor-quality variants (blur/noise/skew)
  datasets/eval/manifest_katanaml.jsonl            ground truth, one JSON object per file
  datasets/eval/katanaml_meta.json                 duplicate groups (original <-> degraded copy)

Usage:  python datasets/tools/fetch_katanaml.py            (needs: pyarrow pillow numpy opencv-python-headless)
"""
from __future__ import annotations

import io
import json
import random
import re
import urllib.request
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import cv2
import numpy as np
import pyarrow.parquet as pq
from PIL import Image

REV = "d2cde298e79c94fb05bc320999deb4b7889b0464"
BASE = f"https://huggingface.co/datasets/katanaml-org/invoices-donut-data-v1/resolve/{REV}/data/"
SPLITS = {
    "test": "test-00000-of-00001-56af6bd5ff7eb34d.parquet",
    "validation": "validation-00000-of-00001-b8a5c4a6237baf25.parquet",
}
ROOT = Path(__file__).resolve().parents[1] / "eval"
OUT = ROOT / "katanaml"
DEGRADED_EVERY = 3  # every 3rd image also gets a degraded copy
rng = random.Random(7)

# Upstream label errors found by auditing every label against the OCR text and the
# invoice arithmetic (see docs/DATASETS.md). Keys: "<split>_<nn>".
LABEL_FIXES: dict[str, dict] = {
    "test_13": {"total": "157929.37", "items": {5: {"amount": "33238.05"}}},  # typo 1579929.37, missing amount
    "validation_06": {"items": {2: {"amount": "29.20"}}},
    "validation_11": {"items": {3: {"amount": "479.80"}}},
    "validation_47": {"items": {0: {"unit_price": "2800.00", "amount": "8400.00"}, 1: {"unit_price": "8400.00"}}},
}


def money(s: str | None) -> str | None:
    """'$ 1 234,56' / '$59,50' / '889,20' -> '1234.56' (string, 2dp)."""
    if s is None or not str(s).strip():
        return None
    t = re.sub(r"[^\d,.\-]", "", str(s))
    if "," in t and "." in t:  # 1.234,56 or 1,234.56
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    else:
        t = t.replace(",", ".")
    return str(Decimal(t).quantize(Decimal("0.01")))


def qty(s: str | None) -> str | None:
    if s is None or not str(s).strip():
        return None
    return str(Decimal(re.sub(r"[^\d,.\-]", "", s).replace(" ", "").replace(",", ".")).normalize())


def convert(gt: dict) -> dict:
    h, items, summ = gt["header"], gt.get("items", []), gt["summary"]
    d = datetime.strptime(h["invoice_date"].strip(), "%m/%d/%Y").date().isoformat()
    total_raw = summ.get("total_gross_worth", "")
    return {
        "invoice_number": h["invoice_no"].strip(),
        "invoice_date": d,
        "supplier_name": h["seller"].strip(),   # GT contains name + address -> eval uses partial match
        "customer_name": h["client"].strip(),
        "currency": "USD",  # every invoice in this set prints "$" on the totals line (3 labels omit it)
        "subtotal": money(summ.get("total_net_worth")),
        "tax": money(summ.get("total_vat")),
        "total": money(total_raw),
        "line_items": [
            {
                "description": it.get("item_desc", "").strip(),
                "quantity": qty(it.get("item_qty")),
                "unit_price": money(it.get("item_net_price")),
                "amount": money(it.get("item_net_worth")),
            }
            for it in items
        ],
    }


def degrade(img: Image.Image) -> Image.Image:
    """Simulate a poor phone/scanner capture: downscale, skew, blur, noise, low contrast."""
    a = np.array(img.convert("L"))
    h, w = a.shape
    a = cv2.resize(a, (int(w * 0.55), int(h * 0.55)), interpolation=cv2.INTER_AREA)  # ~165 dpi
    h, w = a.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), rng.uniform(-2.5, 2.5), 1.0)
    a = cv2.warpAffine(a, m, (w, h), borderValue=235)
    a = cv2.GaussianBlur(a, (3, 3), rng.uniform(0.6, 1.1))
    a = a.astype(np.float32) * rng.uniform(0.75, 0.9) + rng.uniform(15, 35)
    a += np.random.default_rng(rng.randint(0, 10**6)).normal(0, 9, a.shape)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "degraded").mkdir(exist_ok=True)
    rows_out = []
    for split, fname in SPLITS.items():
        cache = OUT / f".{fname}"
        if not cache.exists():
            print("downloading", split)
            urllib.request.urlretrieve(BASE + fname, cache)
        for i, row in enumerate(pq.read_table(cache).to_pylist()):
            raw = json.loads(row["ground_truth"])["gt_parse"]
            if "header" not in raw or "summary" not in raw:
                print(f"skip {split}_{i:02d}: malformed upstream annotation")  # 2 known rows in validation
                continue
            gt = convert(raw)
            fix = LABEL_FIXES.get(f"{split}_{i:02d}", {})
            for k, v in fix.items():
                if k != "items":
                    gt[k] = v
            for idx, upd in fix.get("items", {}).items():
                gt["line_items"][idx].update(upd)
            img = Image.open(io.BytesIO(row["image"]["bytes"])).convert("RGB")
            name = f"{split}_{i:02d}"
            img.save(OUT / f"{name}.jpg", quality=90)
            base = {
                "source": "katanaml",
                "expected_outcome": "success",
                "expected_error": None,
                "invoices": [gt],
                "expected_issues": [],
                "eval_hints": {"supplier_name": "partial", "customer_name": "partial"},
            }
            rows_out.append({"doc_id": f"kat-{name}", "path": f"katanaml/{name}.jpg",
                             "file_type": "jpg", "category": "image_clean", **base})
            if i % DEGRADED_EVERY == 0:
                ext = "tiff" if i % 2 == 0 else "png"
                degrade(img).save(OUT / "degraded" / f"{name}.{ext}", **({"compression": "tiff_adobe_deflate"} if ext == "tiff" else {"optimize": True}))
                rows_out.append({"doc_id": f"kat-{name}-degraded", "path": f"katanaml/degraded/{name}.{ext}",
                                 "file_type": ext, "category": "image_poor_quality", **base})
    with open(ROOT / "manifest_katanaml.jsonl", "w") as f:
        for r in rows_out:
            f.write(json.dumps(r) + "\n")
    # A degraded copy is the same invoice as its original -> the system must flag it as a duplicate.
    groups = [[r["doc_id"].removesuffix("-degraded"), r["doc_id"]] for r in rows_out if r["doc_id"].endswith("-degraded")]
    (ROOT / "katanaml_meta.json").write_text(json.dumps({"duplicate_groups": groups, "crosschecks": []}, indent=2))
    print(f"wrote {len(rows_out)} entries -> {ROOT / 'manifest_katanaml.jsonl'} ({len(groups)} duplicate groups)")


if __name__ == "__main__":
    main()
