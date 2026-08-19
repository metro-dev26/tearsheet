"""
financebench_data.py — load the FinanceBench open subset and pick the rows our
grounding guard can be honestly measured on.

Each row carries the real quote (`evidence_text`) and the full page it came from
(`evidence_text_full_page`), so we ground against text FinanceBench hands us — no
PDF parsing needed. License: CC-BY-NC-4.0 (attribution required, non-commercial).
"""

import json
import re
from pathlib import Path

# Trust the OS certificate store (this machine's network does SSL interception).
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

import requests

from parse_filing import normalize  # the same canonical folding parse() applies

DATA_URL = (
    "https://raw.githubusercontent.com/patronus-ai/financebench/"
    "main/data/financebench_open_source.jsonl"
)
LOCAL_PATH = (
    Path(__file__).resolve().parent.parent
    / "eval" / "financebench" / "financebench_open_source.jsonl"
)
HEADERS = {"User-Agent": "tearsheet-eval Tam sujanss122@gmail.com"}

_NUM_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def download(dest: Path = LOCAL_PATH) -> Path:
    """Fetch the 150-row open subset if it isn't already local. Idempotent."""
    if dest.exists():
        return dest
    resp = requests.get(DATA_URL, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(resp.text, encoding="utf-8")
    return dest


def load_rows(path: Path = LOCAL_PATH) -> list:
    """Read the JSONL into a list of dict rows (one JSON object per line)."""
    text = path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def first_evidence(row: dict):
    """First evidence object carrying BOTH the quote and its full page, else None."""
    for ev in row.get("evidence", []) or []:
        if ev.get("evidence_text") and ev.get("evidence_text_full_page"):
            return ev
    return None


def is_usable(row: dict) -> bool:
    """Usable: a numeric (metrics) question that carries a real quote plus its page."""
    return (
        row.get("question_type") == "metrics-generated"
        and first_evidence(row) is not None
    )


def usable_rows(rows: list) -> list:
    return [r for r in rows if is_usable(r)]


def canonical(text: str) -> str:
    """Fold text to the SAME plain-ASCII, single-spaced form parse() produces."""
    return " ".join(normalize(text).split())


def first_number(text):
    """First number in `text` as a float (commas stripped), or None."""
    m = _NUM_RE.search(text or "")
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None