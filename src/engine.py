"""
engine.py — the SINGLE entry point for running diligence on a filing.

Why this exists (it fixes two things at once):
1. DRIFT. The eval graded the LLM proposer while the Streamlit app ran the old
   Cirrus-tuned regex — so the "honest metric" measured something the demo never
   showed. Both now go through THIS function, so they can't disagree.
2. FLAKINESS. propose() makes a live Gemini call: slow, network-bound, and not
   perfectly deterministic even at temperature 0. Running it on every eval and
   every Streamlit rerun made the whole system depend on a free-tier API being up.
   Here we call the model ONCE per filing and cache the grounded findings to
   eval/cache/<stem>.json. After that the eval is offline and instant, and the live
   demo never touches the network during an interview.

The cache is trusted ONLY if it still verifies:
  - it was built by the same model (_MODEL), AND
  - every cached citation still string-matches the freshly parsed text.
If the parser changed and offsets no longer line up, the cache is stale and we
re-propose. Same spirit as the guard: never trust a citation you can't re-prove.

Refresh the cache deliberately with refresh=True (eval --refresh, below).
"""

import json
from pathlib import Path

from parse_filing import parse
from llm_propose import propose, _MODEL

CACHE_DIR = Path(__file__).resolve().parent.parent / "eval" / "cache"


def _cache_path(filing_path: Path) -> Path:
    return CACHE_DIR / f"{filing_path.stem}.json"


def _citations_still_valid(clean_text: str, findings: dict) -> bool:
    """A cached finding is only trustworthy if its offsets STILL point at its quote
    in the current clean_text. If parsing changed, they won't — treat as stale."""
    for finding in findings.values():
        if finding is None:
            continue
        s, e = finding.get("char_start"), finding.get("char_end")
        if s is None or e is None or clean_text[s:e] != finding.get("snippet"):
            return False
    return True


def _write_cache(filing_path: Path, findings: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(filing_path).write_text(
        json.dumps(
            {"model": _MODEL, "filing": filing_path.name, "findings": findings},
            indent=2,
        ),
        encoding="utf-8",
    )


def get_findings(filing_path: Path, clean_text: str, refresh: bool = False) -> dict:
    """Return {check_name -> finding|None}, from cache when possible.

    Cache is used only when it exists, isn't being force-refreshed, was built by the
    same model, and its citations still verify against clean_text. Otherwise we make
    one live Gemini call, ground it, and write the cache."""
    cp = _cache_path(filing_path)
    if not refresh and cp.exists():
        try:
            cached = json.loads(cp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cached = None
        if (
            cached
            and cached.get("model") == _MODEL
            and _citations_still_valid(clean_text, cached.get("findings", {}))
        ):
            return cached["findings"]

    findings = propose(clean_text)
    _write_cache(filing_path, findings)
    return findings


def run(filing_path: Path, refresh: bool = False):
    """Parse + diligence a filing in one call.

    Returns (clean_text, n_chunks, findings). This is what BOTH the app and the eval
    call, so the number a demo shows and the number the eval grades are the same."""
    clean_text, chunks = parse(filing_path)
    findings = get_findings(filing_path, clean_text, refresh=refresh)
    return clean_text, len(chunks), findings
