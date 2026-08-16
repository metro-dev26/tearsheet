"""
run_eval.py — the HONEST METRIC. Grade the engine against human-keyed truth.

Why this exists (the credibility layer):
Every demo looks right. The question an interviewer (or a buyer) actually asks
is "how do you KNOW it's right?" This harness answers it with numbers instead
of vibes, by comparing what the engine extracts against a GOLD SET — the true
values a human keyed by reading the filing directly (eval/gold/*.json).

Three metrics, each answering a different failure question:

  1. EXTRACTION ACCURACY — of the facts a human keyed from the filing, what
     fraction did the engine extract with exactly the right values?
     (Catches: wrong captures, wrong numbers, missed disclosures.)

  2. CITATION SUPPORTS THE CLAIM — for every finding, does the cited span really
     CONTAIN the number the finding claims? Re-checked here with an INDEPENDENT
     number search, so a bug in the engine's own number-gate can't hide itself.
     (Catches: a real quote paired with a number it doesn't actually contain —
     the crack the guard alone doesn't close.)
     [This replaced the old "offsets slice back to the snippet" check, which
     re-used the same offsets ground() already asserts — it could never fail and
     proved nothing. A metric that can't fail is theater.]

  3. GUARD REJECTION — fed fabricated, plausible-sounding claims (including a
     PARAPHRASE of the real disclosure), does the guard refuse every one? A gold
     file with NO fabricated claims fails: it doesn't exercise the moat at all.

THE CIRCULARITY RULE: gold values must be keyed by a human reading the document,
never produced by the engine. Until a human attests (verified_by_human: true in
the gold file), this harness marks all results PROVISIONAL and exits nonzero.

Findings come from engine.get_findings(), which caches the (single) live Gemini
call to eval/cache/. So this eval is normally OFFLINE, fast, and deterministic.
Regenerate the cache with a fresh model call using:
    /c/Users/sujan/tearsheet/.venv/Scripts/python src/run_eval.py --refresh
"""

import json
import re
import sys
from pathlib import Path

from ground import ground
from parse_filing import parse
from engine import get_findings

GOLD_DIR = Path(__file__).resolve().parent.parent / "eval" / "gold"
FILINGS_DIR = Path(__file__).resolve().parent.parent / "data" / "filings"

# Which numeric fields each check claims — used by metric #2 to confirm every
# claimed number is inside its own citation.
_NUMBER_FIELDS = {
    "customer_concentration": ["pct"],
    "margin_trend": ["cur_pct", "prev_pct"],
}


def compare_field(expected, actual):
    """Compare one gold value against one extracted value.

    Floats get a tiny tolerance (they survive a str->float round trip, not
    arithmetic, so anything beyond noise is a real extraction error). We keep it
    TIGHT on purpose: 41.2 vs 41.15 is a DIFFERENT number, and loosening the
    tolerance to let LLM re-rounding pass would hide exactly the extraction drift
    this eval exists to catch. Strings compare case-insensitively after stripping."""
    if isinstance(expected, float) or isinstance(actual, float):
        try:
            return abs(float(expected) - float(actual)) < 1e-6
        except (TypeError, ValueError):
            return False
    if isinstance(expected, str) and isinstance(actual, str):
        return expected.strip().lower() == actual.strip().lower()
    return expected == actual


def _num_in_span(span: str, value) -> bool:
    """INDEPENDENT re-implementation of the number-in-text check (deliberately not
    imported from llm_propose, so the eval can catch a bug in the engine's own
    gate). True if `value` appears in `span` as a standalone number."""
    if value is None:
        return False
    try:
        n = float(value)
    except (TypeError, ValueError):
        return False
    token = f"{n:g}"
    return re.search(r"(?<![\d.])" + re.escape(token) + r"(?![\d.])", span) is not None


def eval_one(gold_path: Path, refresh: bool = False) -> bool:
    """Run the full eval for one gold file. Returns True if everything passed
    AND the gold set is human-verified."""
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    verified = gold.get("verified_by_human", False)

    filing = FILINGS_DIR / gold["filing"]
    print(f"Filing:   {gold['filing']}")
    print(f"Gold set: {gold_path.name} "
          f"({'HUMAN-VERIFIED' if verified else '*** NOT HUMAN-VERIFIED — PROVISIONAL ***'})")
    print()

    clean_text, _chunks = parse(filing)
    # The REAL engine, via the shared entry point the app also uses (cached; one
    # live Gemini call per filing at most, reused across runs). Same shape the gold
    # compares against, every quote grounded through the guard.
    findings = get_findings(filing, clean_text, refresh=refresh)  # name -> finding|None

    # ---- 1. EXTRACTION ACCURACY -------------------------------------------
    print("== 1. Extraction accuracy (engine vs human-keyed truth) ==")
    correct = total = 0
    for name, spec in gold["checks"].items():
        finding = findings.get(name)

        total += 1
        present_ok = (finding is not None) == spec["expected_present"]
        correct += present_ok
        print(f"  [{'PASS' if present_ok else 'FAIL'}] {name}: present={finding is not None} "
              f"(expected {spec['expected_present']})")

        if finding is None:
            missed = len(spec.get("fields", {}))
            total += missed
            if missed:
                print(f"         -> {missed} field(s) missed (no finding to compare)")
            continue

        for field, expected in spec.get("fields", {}).items():
            total += 1
            actual = finding.get(field)
            ok = compare_field(expected, actual)
            correct += ok
            print(f"  [{'PASS' if ok else 'FAIL'}]   {name}.{field}: "
                  f"got {actual!r}, expected {expected!r}")
    acc = correct / total if total else 0.0
    print(f"  -> extraction accuracy: {correct}/{total} = {acc:.0%}")
    print()

    # ---- 2. CITATION SUPPORTS THE CLAIM -----------------------------------
    # For every finding, the number(s) it claims must physically appear in the
    # cited span — re-checked here independently of the engine's own gate.
    print("== 2. Citation supports the claim (claimed number is inside the cited span) ==")
    cite_ok = cite_total = 0
    for name, finding in findings.items():
        if finding is None:
            continue
        span = clean_text[finding["char_start"]:finding["char_end"]]
        for field in _NUMBER_FIELDS.get(name, []):
            cite_total += 1
            ok = _num_in_span(span, finding.get(field))
            cite_ok += ok
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}.{field}={finding.get(field)!r} "
                  f"in cited span")
        if finding.get("occurrences", 1) > 1:
            print(f"  [warn] {name}: snippet appears {finding['occurrences']}x — "
                  f"citation is ambiguous (cited the first).")
    print(f"  -> citations supporting their claim: {cite_ok}/{cite_total}")
    print()

    # ---- 3. GUARD REJECTION -----------------------------------------------
    print("== 3. Guard rejection (fabricated claims must be refused) ==")
    fakes = gold.get("fabricated_claims", [])
    if not fakes:
        print("  [FAIL] gold set has NO fabricated_claims — the guard is untested here.")
        rej_ok = -1  # force this section to fail below
    else:
        rej_ok = 0
        for fake in fakes:
            refused = ground(clean_text, fake) is None
            rej_ok += refused
            print(f"  [{'PASS' if refused else 'FAIL'}] {'refused' if refused else 'ACCEPTED (BUG!)'}: "
                  f"\"{fake[:70]}{'...' if len(fake) > 70 else ''}\"")
        print(f"  -> guard rejection: {rej_ok}/{len(fakes)}")
    print()

    # ---- verdict -----------------------------------------------------------
    all_pass = (
        (correct == total)
        and (cite_ok == cite_total)
        and (rej_ok == len(fakes))
        and bool(fakes)
    )
    print(f"RESULT: {'ALL PASS' if all_pass else 'FAILURES — see above'}")
    if not verified:
        print("*** PROVISIONAL: gold set not yet human-verified. Open the filing,")
        print("*** confirm every gold value with your own eyes, set")
        print("*** verified_by_human: true, and rerun. Until then this proves nothing.")
    return all_pass and verified


if __name__ == "__main__":
    refresh = "--refresh" in sys.argv[1:]
    gold_files = sorted(GOLD_DIR.glob("*.json"))
    if not gold_files:
        sys.exit(f"No gold files in {GOLD_DIR}")

    # Isolate each filing: one company's network hiccup or bad gold must not abort
    # the whole run. An exception counts as a failure for that filing, and we move on.
    results = []
    for g in gold_files:
        try:
            results.append(eval_one(g, refresh=refresh))
        except Exception as exc:  # noqa: BLE001 — report and keep grading the rest
            print(f"*** ERROR grading {g.name}: {type(exc).__name__}: {exc}")
            print()
            results.append(False)

    passed = sum(1 for r in results if r)
    print(f"==== {passed}/{len(results)} gold sets passed and human-verified ====")
    # Nonzero exit until every gold set passes AND is human-verified — so this can
    # sit in CI later and an unverified/failing eval blocks by default.
    sys.exit(0 if all(results) else 1)
