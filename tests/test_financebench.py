"""
test_financebench.py — OFFLINE tests for the FinanceBench data helpers.

Run (Git Bash):
    /c/Users/sujan/tearsheet/.venv/Scripts/python tests/test_financebench.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from financebench_data import (  # noqa: E402
    is_usable, usable_rows, first_evidence, canonical, first_number,
)

_passed = 0
_failed = 0


def check(name, got, want):
    global _passed, _failed
    if got == want:
        _passed += 1
        print(f"  [PASS] {name}")
    else:
        _failed += 1
        print(f"  [FAIL] {name}\n         got:  {got!r}\n         want: {want!r}")


print("== is_usable / usable_rows / first_evidence ==")
row_ok = {"question_type": "metrics-generated",
          "evidence": [{"evidence_text": "x", "evidence_text_full_page": "y"}]}
row_wrong_type = {"question_type": "novel-generated",
                  "evidence": [{"evidence_text": "x", "evidence_text_full_page": "y"}]}
row_no_ev = {"question_type": "metrics-generated", "evidence": []}
row_partial = {"question_type": "metrics-generated",
               "evidence": [{"evidence_text": "x", "evidence_text_full_page": ""}]}

check("usable row is usable", is_usable(row_ok), True)
check("wrong question_type not usable", is_usable(row_wrong_type), False)
check("no evidence not usable", is_usable(row_no_ev), False)
check("partial evidence not usable", is_usable(row_partial), False)
check("usable_rows filters to the good row", usable_rows([row_ok, row_wrong_type, row_no_ev]), [row_ok])
check("first_evidence returns the complete one", first_evidence(row_ok)["evidence_text"], "x")
check("first_evidence is None when partial", first_evidence(row_partial), None)

print("== canonical ==")
check("canonical collapses whitespace", canonical("a   b\nc"), "a b c")
check("canonical folds a curly apostrophe", canonical("Company’s"), "Company's")

print("== first_number ==")
check("plain percent", first_number("Apple was 67% of revenue"), 67.0)
check("decimal", first_number("margin of 41.2%"), 41.2)
check("strips thousands comma", first_number("$1,577 million"), 1577.0)
check("none when no digits", first_number("no digits here"), None)

print(f"\nRESULT: {_passed} passed, {_failed} failed")
sys.exit(1 if _failed else 0)