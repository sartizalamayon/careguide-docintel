"""End-to-end evaluation runner (SPEC §14).

Uploads every manifest file through the REST API, waits for the documents to finish, scores the extracted
invoices against the manifest ground truth and writes metrics.json, per_document.csv and report.md.

    python /eval/run_eval.py --api http://localhost:8000 --manifests <jsonl...> --out <dir>

Uploaded files are named "<doc_id><extension>" so that every file in a request has a unique name.
The run is resumable: upload and completion records are kept in <out>/state.json.
"""

from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

try:
    import metrics
except ImportError:
    from eval import metrics

API_PREFIX = "/api/v1"
BATCH_SIZE = 5
TERMINAL = frozenset({"completed", "needs_review", "failed"})
SCORED_STATUSES = frozenset({"completed", "needs_review"})
TIMEOUT_S = 30 * 60
POLL_INTERVAL_S = 2.0
STATE_FILE = "state.json"

Row = dict[str, Any]


@dataclass
class DocResult:
    row: Row
    status: str
    error_code: str | None = None
    document_id: str | None = None
    wall_s: float | None = None
    processing_ms: int | None = None
    pages_total: int | None = None
    invoices: list[dict[str, Any]] = field(default_factory=list)
    score: metrics.DocScore | None = None

    @property
    def doc_id(self) -> str:
        return self.row["doc_id"]

    @property
    def expected_success(self) -> bool:
        return self.row["expected_outcome"] == "success"


# ---------------------------------------------------------------- inputs and state


def load_manifest(path: Path) -> list[Row]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in rows:
        row["abs_path"] = str(path.parent / row["path"])
    return rows


def load_meta(manifest: Path) -> dict[str, Any]:
    """manifest_<name>.jsonl is described by <name>_meta.json in the same folder, when it exists."""
    meta_path = manifest.with_name(manifest.stem.removeprefix("manifest_") + "_meta.json")
    if not meta_path.exists():
        return {"duplicate_groups": [], "crosschecks": []}
    return json.loads(meta_path.read_text(encoding="utf-8"))


def load_state(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"docs": {}, "http_5xx": 0}


def save_state(path: Path, state: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1), encoding="utf-8")
    tmp.replace(path)


def make_client(api: str, api_key: str, state: dict[str, Any]) -> httpx.Client:
    def count_5xx(response: httpx.Response) -> None:
        if response.status_code >= 500:
            state["http_5xx"] += 1

    return httpx.Client(
        base_url=api.rstrip("/") + API_PREFIX,
        headers={"X-API-Key": api_key},
        timeout=httpx.Timeout(120.0, connect=10.0),
        event_hooks={"response": [count_5xx]},
    )


def get_json(client: httpx.Client, path: str) -> Any | None:
    try:
        response = client.get(path)
    except httpx.HTTPError:
        return None
    return response.json() if response.status_code == 200 else None


# ---------------------------------------------------------------- step 1: upload


def upload_name(row: Row) -> str:
    return row["doc_id"] + Path(row["path"]).suffix


def upload_batch(client: httpx.Client, batch: list[Row]) -> dict[str, dict[str, Any]]:
    """Upload up to five rows in one request; return a state entry per doc_id that reached the API."""
    files = [
        (
            "files",
            (
                upload_name(r),
                Path(r["abs_path"]).read_bytes(),
                mimetypes.guess_type(r["path"])[0] or "application/octet-stream",
            ),
        )
        for r in batch
    ]
    started = time.time()
    try:
        response = client.post("/documents", files=files)
    except httpx.HTTPError as exc:
        print(f"upload failed for {[r['doc_id'] for r in batch]}: {exc.__class__.__name__}", flush=True)
        return {}
    try:
        body = response.json()
    except ValueError:
        body = {}
    accepted = {d["filename"]: d["id"] for d in body.get("documents", [])}
    rejected = {d["filename"]: d["code"] for d in body.get("rejected", [])}
    fallback = f"HTTP_{response.status_code}"
    entries: dict[str, dict[str, Any]] = {}
    for row in batch:
        name = upload_name(row)
        entries[row["doc_id"]] = {
            "document_id": accepted.get(name),
            "rejected_code": None if name in accepted else rejected.get(name, fallback),
            "uploaded_at": started,
            "final": None,
        }
    return entries


def upload_pending(client: httpx.Client, rows: list[Row], state: dict[str, Any], state_path: Path) -> None:
    pending = []
    for row in rows:
        if row["doc_id"] in state["docs"]:
            continue
        if Path(row["abs_path"]).is_file():
            pending.append(row)
        else:
            print(f"{row['doc_id']} missing local file {row['path']}", flush=True)
    for start in range(0, len(pending), BATCH_SIZE):
        entries = upload_batch(client, pending[start : start + BATCH_SIZE])
        state["docs"].update(entries)
        save_state(state_path, state)
        for doc_id, entry in entries.items():
            if entry["rejected_code"]:
                print(f"{doc_id} rejected {entry['rejected_code']}", flush=True)


# ---------------------------------------------------------------- step 2: poll


def final_record(body: dict[str, Any] | None, wall_s: float, status: str | None = None) -> dict[str, Any]:
    body = body or {}
    return {
        "status": status or body["status"],
        "error_code": body.get("error_code"),
        "pages_done": body.get("pages_done"),
        "pages_total": body.get("pages_total"),
        "wall_s": wall_s,
    }


def wait_for_terminal(client: httpx.Client, state: dict[str, Any], state_path: Path) -> None:
    pending = [d for d, e in state["docs"].items() if e["document_id"] and e["final"] is None]
    while pending:
        remaining = []
        for doc_id in pending:
            entry = state["docs"][doc_id]
            body = get_json(client, f"/documents/{entry['document_id']}/status")
            wall_s = time.time() - entry["uploaded_at"]
            if body and body["status"] in TERMINAL:
                entry["final"] = final_record(body, wall_s)
            elif wall_s > TIMEOUT_S:
                entry["final"] = final_record(body, wall_s, status="timeout")
            else:
                remaining.append(doc_id)
                continue
            print(f"{doc_id} {entry['final']['status']} {wall_s:.1f}s", flush=True)
        save_state(state_path, state)
        pending = remaining
        if pending:
            time.sleep(POLL_INTERVAL_S)


# ---------------------------------------------------------------- step 3: fetch and score


def fetch_invoices(client: httpx.Client, detail: dict[str, Any]) -> list[dict[str, Any]]:
    summaries = sorted(detail.get("invoices", []), key=lambda s: s["seq"])
    fetched = (get_json(client, f"/invoices/{s['id']}") for s in summaries)
    return [invoice for invoice in fetched if invoice is not None]


def collect(client: httpx.Client, row: Row, entry: dict[str, Any] | None) -> DocResult:
    if entry is None:
        return DocResult(row, status="not_uploaded")
    if entry["rejected_code"]:
        return DocResult(row, status="rejected", error_code=entry["rejected_code"])
    final = entry["final"]
    result = DocResult(
        row,
        status=final["status"],
        error_code=final["error_code"],
        document_id=entry["document_id"],
        wall_s=final["wall_s"],
        pages_total=final["pages_total"],
    )
    detail = get_json(client, f"/documents/{entry['document_id']}") if final["status"] in TERMINAL else None
    if detail:
        result.processing_ms = detail.get("processing_ms")
        result.pages_total = detail.get("pages_total", result.pages_total)
        if final["status"] in SCORED_STATUSES:
            result.invoices = fetch_invoices(client, detail)
    if result.expected_success:
        result.score = metrics.score_document(row["invoices"], result.invoices, row.get("eval_hints", {}))
    return result


# ---------------------------------------------------------------- aggregation


def extraction_summary(results: list[DocResult]) -> dict[str, Any]:
    tallies: dict[str, metrics.Tally] = defaultdict(metrics.Tally)
    for r in results:
        if r.score is not None:
            for group in ("all", r.row["source"], f"{r.row['source']}/{r.row['category']}"):
                tallies[group].add(r.score)
    return {group: tally.summary() for group, tally in sorted(tallies.items())}


def validation_summary(results: list[DocResult]) -> dict[str, Any]:
    expected: set[metrics.IssueKey] = set()
    observed: set[metrics.IssueKey] = set()
    for r in results:
        if r.score is None:
            continue
        expected |= metrics.expected_issue_keys(r.doc_id, r.row["invoices"], r.row.get("expected_issues", []))
        for gt_index, pred_index in r.score.matches.items():
            observed |= metrics.observed_issue_keys(r.doc_id, gt_index, r.invoices[pred_index].get("issues", []))
    return metrics.score_issue_sets(expected, observed).as_dict()


def duplicate_groups(results: list[DocResult], metas: list[dict[str, Any]]) -> list[list[str]]:
    present = {r.doc_id for r in results if r.document_id}
    groups = [g for meta in metas for g in meta["duplicate_groups"]]
    return [g for g in groups if all(doc in present for doc in g)]


def duplicate_flags(results: list[DocResult]) -> list[tuple[str, str | None]]:
    by_api_id = {r.document_id: r.doc_id for r in results if r.document_id}
    flags = []
    for r in results:
        for invoice in r.invoices:
            for issue in invoice.get("issues", []):
                if issue["code"] == "DUPLICATE_INVOICE":
                    other = issue.get("details", {}).get("duplicate_of_document_id")
                    flags.append((r.doc_id, by_api_id.get(other, other)))
    return flags


def run_crosschecks(
    client: httpx.Client, results: list[DocResult], metas: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    api_ids = {r.doc_id: r.document_id for r in results if r.status in SCORED_STATUSES}
    outcomes = []
    for check in (c for meta in metas for c in meta["crosschecks"]):
        a, b = api_ids.get(check["a"]), api_ids.get(check["b"])
        outcome: dict[str, Any] = {"a": check["a"], "b": check["b"], "kind": check["kind"]}
        if a is None or b is None:
            differences = ["a document is not completed or was not uploaded"]
        else:
            response = client.post("/cross-checks", json={"document_a_id": a, "document_b_id": b})
            if response.status_code == 201:
                differences = metrics.crosscheck_differences(check["expected"], response.json()["summary"])
            else:
                differences = [f"HTTP {response.status_code}"]
        outcomes.append({**outcome, "passed": not differences, "differences": differences})
    return outcomes


def fault_invoice_count(results: list[DocResult], in_duplicate_group: set[str]) -> tuple[int, int]:
    """Return (invoices routed to review, of which carry an injected fault or are a known duplicate)."""
    reviewed = faulty = 0
    for r in results:
        if r.score is None:
            continue
        keys = metrics.expected_issue_keys(r.doc_id, r.row["invoices"], r.row.get("expected_issues", []))
        faulty_gt = {k[1] for k in keys}
        if r.doc_id in in_duplicate_group:
            faulty_gt = set(range(len(r.row["invoices"])))
        for gt_index, pred_index in r.score.matches.items():
            if r.invoices[pred_index]["status"] == "needs_review":
                reviewed += 1
                faulty += gt_index in faulty_gt
    return reviewed, faulty


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def operational_summary(results: list[DocResult], groups: list[list[str]]) -> dict[str, Any]:
    valid = [r for r in results if r.expected_success]

    def count(status: str) -> int:
        return sum(r.status == status for r in valid)

    reviewed, faulty = fault_invoice_count(results, {d for g in groups for d in g})
    invalid = [r for r in results if not r.expected_success]
    handled = sum(r.error_code == r.row["expected_error"] for r in invalid)
    return {
        "valid_documents": len(valid),
        "completed": count("completed"),
        "needs_review": count("needs_review"),
        "failed": count("failed"),
        "rejected_at_upload": count("rejected"),
        "success_rate": _rate(count("completed") + count("needs_review"), len(valid)),
        "failure_rate": _rate(count("failed"), len(valid)),
        "document_review_rate": _rate(count("needs_review"), len(valid)),
        "invoices_routed_to_review": reviewed,
        "invoices_routed_to_review_with_known_fault": faulty,
        "invalid_documents": len(invalid),
        "graceful_handling": {"handled": handled, "total": len(invalid), "rate": _rate(handled, len(invalid))},
        "stuck_documents": sum(r.status in {"queued", "processing", "timeout"} for r in results),
    }


def percentile_pair(values: list[float]) -> dict[str, float | None]:
    return {"p50": metrics.p50(values), "p95": metrics.p95(values)}


def timing_for(results: list[DocResult]) -> dict[str, Any]:
    timed = [r for r in results if r.processing_ms is not None]
    per_page = [r.processing_ms / 1000 / r.pages_total for r in timed if r.pages_total]
    pages = sum(r.pages_total or 0 for r in timed)
    minutes = sum(r.processing_ms for r in timed) / 60000
    return {
        "documents": len(timed),
        "pages": pages,
        "processing_s_per_document": percentile_pair([r.processing_ms / 1000 for r in timed]),
        "processing_s_per_page": percentile_pair(per_page),
        "wall_s_per_document": percentile_pair([r.wall_s for r in timed if r.wall_s is not None]),
        "pages_per_minute": pages / minutes if minutes else None,
        "invoices_expected": sum(len(r.row["invoices"]) for r in timed),
        "invoices_predicted": sum(len(r.invoices) for r in timed),
    }


def performance_summary(results: list[DocResult]) -> dict[str, Any]:
    valid = [r for r in results if r.expected_success and r.status in TERMINAL]
    by_category: dict[str, list[DocResult]] = defaultdict(list)
    for r in valid:
        by_category[r.row["category"]].append(r)
    return {"all": timing_for(valid), "by_category": {c: timing_for(rs) for c, rs in sorted(by_category.items())}}


# ---------------------------------------------------------------- step 4: outputs

CSV_COLUMNS = [
    "doc_id",
    "category",
    "expected_outcome",
    "expected_error",
    "status",
    "error_code",
    "invoices_expected",
    "invoices_predicted",
    "fields_correct",
    "fields_total",
    "processing_ms",
    "pages_total",
    "wall_s",
]


def csv_row(r: DocResult) -> dict[str, Any]:
    score = r.score
    return {
        "doc_id": r.doc_id,
        "category": r.row["category"],
        "expected_outcome": r.row["expected_outcome"],
        "expected_error": r.row["expected_error"],
        "status": r.status,
        "error_code": r.error_code,
        "invoices_expected": len(r.row["invoices"]),
        "invoices_predicted": len(r.invoices),
        "fields_correct": score.correct_count if score else None,
        "fields_total": score.total_count if score else None,
        "processing_ms": r.processing_ms,
        "pages_total": r.pages_total,
        "wall_s": None if r.wall_s is None else f"{r.wall_s:.1f}",
    }


def write_csv(path: Path, results: list[DocResult]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, restval="")
        writer.writeheader()
        writer.writerows(csv_row(r) for r in results)


def fmt(value: Any, percent: bool = False) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.1%}" if percent else f"{value:.2f}"
    return str(value)


def table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def extraction_tables(extraction: dict[str, Any]) -> str:
    columns = [g for g in extraction if g in {"all", "synthetic"} or g.startswith("katanaml")]
    field_rows = [
        [name, *(fmt(extraction[g]["field_accuracy"][name]["accuracy"], True) for g in columns)]
        for name in metrics.FIELDS
    ]
    field_rows.append(["micro average", *(fmt(extraction[g]["micro_accuracy"], True) for g in columns)])
    group_rows = []
    for group, s in extraction.items():
        lines = s["line_items"]
        group_rows.append(
            [
                group,
                s["documents"],
                fmt(s["micro_accuracy"], True),
                fmt(s["document_exact_match"]["rate"], True),
                fmt(lines["precision"], True),
                fmt(lines["recall"], True),
                fmt(lines["f1"], True),
                fmt(s["hallucination"]["rate"], True),
                f"{s['invoices']['matched']}/{s['invoices']['expected']}",
            ]
        )
    group_headers = [
        "Group",
        "Docs",
        "Field acc.",
        "Exact match",
        "Line P",
        "Line R",
        "Line F1",
        "Hallucination",
        "Invoices matched",
    ]
    return "\n\n".join(
        [
            "### Field accuracy\n\n" + table(["Field", *columns], field_rows),
            "### By group\n\n" + table(group_headers, group_rows),
        ]
    )


def validation_tables(doc: dict[str, Any]) -> str:
    val, dup = doc["validation"], doc["duplicates"]
    checks = [
        ["Arithmetic and field rules", fmt(val["precision"], True), fmt(val["recall"], True)]
        + [f"TP {val['tp']}, FP {val['fp']}, FN {val['fn']}"],
        ["Duplicate detection", fmt(dup["precision"], True), fmt(dup["recall"], True)]
        + [f"{dup['detected_groups']}/{dup['groups']} groups, {dup['flagged'] - dup['correct_flags']} false flags"],
    ]
    pairs = [
        [f"{c['a']} vs {c['b']}", c["kind"], "pass" if c["passed"] else "fail", "; ".join(c["differences"])]
        for c in doc["crosschecks"]
    ]
    return (
        table(["Check", "Precision", "Recall", "Counts"], checks)
        + "\n\n"
        + table(["Cross-check pair", "Kind", "Result", "Differences"], pairs)
    )


def operations_table(doc: dict[str, Any]) -> str:
    op = doc["operational"]
    graceful = op["graceful_handling"]
    rows = [
        ["Valid documents", op["valid_documents"]],
        [
            "Completed / needs review / failed / rejected",
            f"{op['completed']} / {op['needs_review']} / {op['failed']} / {op['rejected_at_upload']}",
        ],
        ["Success rate", fmt(op["success_rate"], True)],
        ["Failure rate", fmt(op["failure_rate"], True)],
        ["Document review rate", fmt(op["document_review_rate"], True)],
        [
            "Invoices routed to review (with known fault)",
            f"{op['invoices_routed_to_review']} ({op['invoices_routed_to_review_with_known_fault']})",
        ],
        ["Graceful handling of invalid files", f"{graceful['handled']}/{graceful['total']}"],
        ["HTTP 5xx responses", doc["http_5xx"]],
        ["Stuck documents", op["stuck_documents"]],
    ]
    return table(["Metric", "Value"], rows)


def performance_table(performance: dict[str, Any]) -> str:
    rows = []
    for name, t in {"all": performance["all"], **performance["by_category"]}.items():
        per_doc, per_page = t["processing_s_per_document"], t["processing_s_per_page"]
        rows.append(
            [
                name,
                t["documents"],
                t["pages"],
                fmt(per_doc["p50"]),
                fmt(per_doc["p95"]),
                fmt(per_page["p50"]),
                fmt(per_page["p95"]),
                fmt(t["pages_per_minute"]),
                f"{t['invoices_predicted']}/{t['invoices_expected']}",
            ]
        )
    headers = [
        "Category",
        "Docs",
        "Pages",
        "Doc p50",
        "Doc p95",
        "Page p50",
        "Page p95",
        "Pages/min",
        "Invoices found/expected",
    ]
    return table(headers, rows)


def render_report(doc: dict[str, Any]) -> str:
    run_info = doc["run"]
    llm = (
        "Not reported by `/api/v1/stats`."
        if doc["llm"] is None
        else f"```json\n{json.dumps(doc['llm'], indent=1)}\n```"
    )
    sections = [
        "# Evaluation run\n\n"
        f"Started {run_info['started_at']}, finished {run_info['finished_at']}, API {run_info['api']}. "
        f"{run_info['documents']} manifest documents, {run_info['not_uploaded']} not uploaded.",
        "## 1. Extraction accuracy\n\n" + extraction_tables(doc["extraction"]),
        "## 2. Validation\n\n" + validation_tables(doc),
        "## 3. Robustness and operations\n\n" + operations_table(doc),
        "## 4. Performance (processing time in seconds)\n\n" + performance_table(doc["performance"]),
        "## 5. LLM usage\n\n" + llm,
    ]
    return "\n\n".join(sections) + "\n"


# ---------------------------------------------------------------- main


def run(args: argparse.Namespace) -> None:
    api_key = os.environ.get("API_KEY")
    if not api_key:
        sys.exit("API_KEY is not set")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    state_path = out / STATE_FILE
    state = load_state(state_path)
    manifests = [Path(m) for m in args.manifests]
    rows = [row for m in manifests for row in load_manifest(m)]
    metas = [load_meta(m) for m in manifests]
    started_at = datetime.now(UTC).isoformat(timespec="seconds")

    with make_client(args.api, api_key, state) as client:
        upload_pending(client, rows, state, state_path)
        wait_for_terminal(client, state, state_path)
        results = [collect(client, row, state["docs"].get(row["doc_id"])) for row in rows]
        attempted = [r for r in results if r.status != "not_uploaded"]
        groups = duplicate_groups(attempted, metas)
        crosschecks = run_crosschecks(client, attempted, metas)
        stats = get_json(client, "/stats")
    save_state(state_path, state)

    metrics_doc = {
        "run": {
            "api": args.api,
            "manifests": [str(m) for m in manifests],
            "started_at": started_at,
            "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "documents": len(results),
            "not_uploaded": len(results) - len(attempted),
        },
        "extraction": extraction_summary(attempted),
        "validation": validation_summary(attempted),
        "duplicates": metrics.score_duplicates(groups, duplicate_flags(attempted)).as_dict(),
        "crosschecks": crosschecks,
        "crosschecks_passed": sum(c["passed"] for c in crosschecks),
        "operational": operational_summary(attempted, groups),
        "performance": performance_summary(attempted),
        "http_5xx": state["http_5xx"],
        "llm": (stats or {}).get("llm"),
        "api_stats": stats,
    }
    (out / "metrics.json").write_text(json.dumps(metrics_doc, indent=2), encoding="utf-8")
    write_csv(out / "per_document.csv", results)
    (out / "report.md").write_text(render_report(metrics_doc), encoding="utf-8")
    print(f"wrote {out}/metrics.json, per_document.csv, report.md", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="DocIntel end-to-end evaluation")
    parser.add_argument("--api", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--manifests", nargs="+", required=True, help="manifest_*.jsonl files")
    parser.add_argument("--out", required=True, help="output directory (also holds state.json)")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
