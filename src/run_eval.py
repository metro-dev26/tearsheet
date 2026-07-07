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
     (Catches: wrong regex captures, wrong numbers, missed disclosures.)

  2. CITATION VALIDITY — for every citation the engine emitted, do the
     character offsets REALLY point at the quoted words? Re-verified here,
     independently of the guard's own assert.
     (Catches: offset bugs — the failure that would make citations lies.)

  3. GUARD REJECTION — fed fabricated, plausible-sounding claims (including a
     PARAPHRASE of the real disclosure), does the guard refuse every one?
     (Catches: the guard going soft — the failure that would admit hallucinations.)

THE CIRCULARITY RULE: gold values must be keyed by a human reading the document,
never produced by the engine. Until a human attests (verified_by_human: true in
the gold file), this harness marks all results PROVISIONAL and exits nonzero —
an unverified eval refusing to be trusted is the same philosophy as the guard.

Run (Git Bash):
    /c/Users/sujan/tearsheet/.venv/Scripts/python src/run_eval.py
"""

import json
import sys
from pathlib import Path

from ground import ground
from parse_filing import parse
from run_diligence import run_all_checks

GOLD_DIR = Path(__file__).resolve().parent.parent / "eval" / "gold"
FILINGS_DIR = Path(__file__).resolve().parent.parent / "data" / "filings"


def compare_field(expected, actual):
    """Compare one gold value against one extracted value.

    Floats get a tiny tolerance (they survive a str->float round trip, not
    arithmetic, so anything beyond noise is a real extraction error). Strings
    compare case-insensitively after stripping — 'Apple Inc.' vs 'apple inc.'
    is a formatting difference, not a wrong answer."""
    if isinstance(expected, float) or isinstance(actual, float):
        try:
            return abs(float(expected) - float(actual)) < 1e-6
        except (TypeError, ValueError):
            return False
    if isinstance(expected, str) and isinstance(actual, str):
        return expected.strip().lower() == actual.strip().lower()
    return expected == actual


def eval_one(gold_path: Path) -> bool:
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
    findings = dict(run_all_checks(clean_text))  # name -> finding-or-None

    # ---- 1. EXTRACTION ACCURACY -------------------------------------------
    # Field-by-field against the gold values. Every mismatch is printed —
    # an aggregate score with hidden failures would be exactly the kind of
    # dishonesty this project exists to prevent.
    print("== 1. Extraction accuracy (engine vs human-keyed truth) ==")
    correct = total = 0
    for name, spec in gold["checks"].items():
        finding = findings.get(name)

        # Presence itself is a graded fact: the human says this disclosure
        # exists — did the engine surface it at all?
        total += 1
        present_ok = (finding is not None) == spec["expected_present"]
        correct += present_ok
        print(f"  [{'PASS' if present_ok else 'FAIL'}] {name}: present={finding is not None} "
              f"(expected {spec['expected_present']})")

        if finding is None:
            # Engine found nothing; every gold field it should have extracted
            # counts as a miss. No partial credit for silence.
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

    # ---- 2. CITATION VALIDITY ---------------------------------------------
    # Re-check every emitted citation from scratch: the characters at the
    # cited offsets must equal the quoted snippet. The guard already asserts
    # this internally; re-verifying here means even a bug in the guard itself
    # can't slip a bad citation past the eval.
    print("== 2. Citation validity (offsets really point at the quote) ==")
    cite_ok = cite_total = 0
    for name, finding in findings.items():
        if finding is None:
            continue
        cite_total += 1
        ok = clean_text[finding["char_start"]:finding["char_end"]] == finding["snippet"]
        cite_ok += ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: "
              f"chars {finding['char_start']:,}-{finding['char_end']:,}")
    print(f"  -> citation validity: {cite_ok}/{cite_total}")
    print()

    # ---- 3. GUARD REJECTION -----------------------------------------------
    # Every fabricated claim must be refused. A single acceptance means the
    # guard would let a hallucination through — instant fail.
    print("== 3. Guard rejection (fabricated claims must be refused) ==")
    rej_ok = 0
    fakes = gold.get("fabricated_claims", [])
    for fake in fakes:
        refused = ground(clean_text, fake) is None
        rej_ok += refused
        print(f"  [{'PASS' if refused else 'FAIL'}] {'refused' if refused else 'ACCEPTED (BUG!)'}: "
              f"\"{fake[:70]}{'...' if len(fake) > 70 else ''}\"")
    print(f"  -> guard rejection: {rej_ok}/{len(fakes)}")
    print()

    # ---- verdict -----------------------------------------------------------
    all_pass = (correct == total) and (cite_ok == cite_total) and (rej_ok == len(fakes))
    print(f"RESULT: {'ALL PASS' if all_pass else 'FAILURES — see above'}")
    if not verified:
        print("*** PROVISIONAL: gold set not yet human-verified. Open the filing,")
        print("*** confirm every gold value with your own eyes, set")
        print("*** verified_by_human: true, and rerun. Until then this proves nothing.")
    return all_pass and verified


if __name__ == "__main__":
    gold_files = sorted(GOLD_DIR.glob("*.json"))
    if not gold_files:
        sys.exit(f"No gold files in {GOLD_DIR}")

    results = [eval_one(g) for g in gold_files]
    # Nonzero exit until every gold set passes AND is human-verified — so this
    # can sit in CI later and an unverified/failing eval blocks by default.
    sys.exit(0 if all(results) else 1)
