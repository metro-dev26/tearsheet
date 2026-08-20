"""
run_financebench_eval.py — EXTERNAL validation of the grounding guard.

Tearsheet's internal eval grades the guard against fabricated claims WE wrote.
Fair criticism: "you passed your own test." This harness answers it by measuring
the SAME guard against real financial claims from a public benchmark (FinanceBench,
Patronus AI, CC-BY-NC-4.0) that we did not author.

Two metrics — and neither is a tautology (a metric that can't fail is theater):

  A. GROUNDING ROBUSTNESS — of real evidence quotes from unseen companies, what
     fraction ground verbatim in their own page after the same canonical folding
     parse() applies?

  B. EXTRACTABILITY SPLIT — of numeric answers, what fraction have their value
     STATED in the cited statement (Tearsheet's extract-and-ground lane) vs DERIVED
     (a ratio / per-share / cross-statement / rounded figure — which Tearsheet
     refuses to fabricate)?

Why Metric B compares NUMBERS, not strings: FinanceBench statements print figures
as "1,577" / "8.70" / "$1,616". A raw string search for "1577" is blind to commas
and trailing zeros, so it miscounts stated numbers as "derived" — a measurement
artifact, not a real refusal. We instead parse every number in the quote to a float
and test the claimed value for membership. (NOTE: Tearsheet's PRODUCTION guard check
`_number_in` in llm_propose.py has that same comma blind spot — a real, fail-safe
coverage bug tracked for its own fix; we do NOT want to inherit it into this
measurement.) No rounding tolerance: a rounded answer (1616 vs a stated 1,615.9) is
DERIVED on purpose — claiming it verbatim would be the exact fabrication the guard exists to stop.

Run (Git Bash):
    /c/Users/sujan/tearsheet/.venv/Scripts/python src/run_financebench_eval.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ground import ground
from financebench_data import (
    download, load_rows, usable_rows, first_evidence, canonical, first_number,
)

_NUM = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def values_in(text: str) -> set:
    """Every number in `text` as a float (commas stripped). Comparing VALUES, not
    strings, is what makes '1,577' and '1577' the same number."""
    out = set()
    for m in _NUM.finditer(text or ""):
        try:
            out.add(float(m.group(0).replace(",", "")))
        except ValueError:
            pass
    return out


def main() -> int:
    path = download()
    rows = load_rows(path)
    usable = usable_rows(rows)
    print(f"FinanceBench open subset: {len(rows)} rows; "
          f"{len(usable)} usable (metrics-generated with evidence).")
    if not usable:
        print("*** No usable rows — cannot measure the guard. ***")
        return 1
    print()

    # ---- Metric A: grounding robustness -------------------------------------
    print("== Metric A: grounding robustness (real quote grounds in its own page) ==")
    accept_ok = 0
    over_refusals = []
    for row in usable:
        ev = first_evidence(row)
        page = canonical(ev["evidence_text_full_page"])
        if ground(page, ev["evidence_text"]) is not None:
            accept_ok += 1
        else:
            over_refusals.append(row.get("financebench_id", "?"))
    n = len(usable)
    print(f"  grounded {accept_ok}/{n} = {accept_ok / n:.0%} of real quotes "
          f"(over-refusals: {len(over_refusals)})")
    if over_refusals:
        shown = ", ".join(str(x) for x in over_refusals[:10])
        more = " ..." if len(over_refusals) > 10 else ""
        print(f"  over-refused ids (normalization cost): {shown}{more}")
    print()

    # ---- Metric B: extractability split -------------------------------------
    print("== Metric B: extractability split (is the answer's value stated in the cited quote?) ==")
    extractable = derived = no_number = 0
    for row in usable:
        ev = first_evidence(row)
        claim = first_number(row.get("answer", ""))
        if claim is None:
            no_number += 1
            continue
        if claim in values_in(ev["evidence_text"]):
            extractable += 1
        else:
            derived += 1
    judged = extractable + derived
    if judged:
        print(f"  extractable (value stated in the statement): {extractable}/{judged} = {extractable / judged:.0%}")
        print(f"  derived (computed — refused, not fabricated): {derived}/{judged} = {derived / judged:.0%}")
    print(f"  (answers with no parseable number, excluded: {no_number})")
    print()

    print("Data: FinanceBench (Patronus AI), CC-BY-NC-4.0 — "
          "https://huggingface.co/datasets/PatronusAI/financebench")
    return 0


if __name__ == "__main__":
    sys.exit(main())