"""
test_ground.py — OFFLINE tests for the guard and the number-in-citation check.

Why this file exists:
The guard (ground.py) and the number check (_number_in in llm_propose.py) are the
whole trust story of Tearsheet — "every claim traced to the exact line, and the
line actually contains the number." Until now the ONLY thing exercising them was
run_eval.py, which makes a LIVE Gemini call per filing: slow, network-bound, and
non-deterministic. You could not test the guard's own logic without the internet.

This script does. No network, no API key, no model — just hand-built strings and
the pure functions, so it runs in a blink and pins the behavior down. Same harness
style as run_eval.py (plain asserts, a PASS/FAIL tally, nonzero exit on any
failure) so it can gate CI later. Deliberately no pytest — not worth a dependency
for a file this small, and the project already hand-rolls its harnesses.

Run (Git Bash):
    /c/Users/sujan/tearsheet/.venv/Scripts/python tests/test_ground.py
"""

import sys
from pathlib import Path

# The engine modules use bare imports (`from parse_filing import ...`) and assume
# src/ is on the path. Put it there so this test can import them from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from parse_filing import normalize          # noqa: E402
from ground import ground                    # noqa: E402
from llm_propose import _number_in, _ground_concentration, _ground_margin  # noqa: E402


# --- tiny test harness ------------------------------------------------------
_passed = 0
_failed = 0


def check(name: str, got, want):
    global _passed, _failed
    if got == want:
        _passed += 1
        print(f"  [PASS] {name}")
    else:
        _failed += 1
        print(f"  [FAIL] {name}\n         got:  {got!r}\n         want: {want!r}")


# --- 1. ground(): the guard --------------------------------------------------
print("== ground() — the guard ==")

# Exact match returns real, checkable offsets.
ct = "one end customer, Apple Inc., represented approximately 91 percent of net sales."
cite = ground(ct, "represented approximately 91 percent")
check("exact match returns a cite", cite is not None, True)
check("offsets slice back to the snippet", ct[cite["char_start"]:cite["char_end"]], cite["snippet"])

# Curly punctuation folds to plain ASCII, so a true quote isn't falsely refused
# over a smart apostrophe. clean_text is already normalized; the snippet arrives curly.
ct_norm = normalize("the Company’s largest customer")     # -> straight quote
cite_curly = ground(ct_norm, "the Company’s largest customer")  # curly in the query
check("curly-quote snippet still grounds", cite_curly is not None, True)

# A quote that isn't in the text is refused. Refusing is the feature.
check("absent snippet is refused", ground(ct, "Samsung represented 45 percent"), None)

# Finding #6: .find() cites the FIRST occurrence. We no longer hide that — a
# duplicate snippet cites instance #1 AND reports how many times it appears, so an
# ambiguous citation can be flagged instead of trusted blind.
dup = "the cat sat. the cat ran."
dup_cite = ground(dup, "the cat")
check("duplicate snippet cites the FIRST instance", dup_cite["char_start"], 0)
check("duplicate snippet reports occurrence count", dup_cite["occurrences"], 2)
check("unique snippet reports occurrences == 1", ground(dup, "the cat sat")["occurrences"], 1)

# Finding #5 FIXED: ground() now collapses whitespace to the parser's canonical
# single-space form, so a quote pulled from a multi-cell table (double spaces /
# newlines) grounds instead of being falsely refused. Still exact on visible chars.
check("double-space snippet now grounds", ground("44.2 % margin", "44.2  % margin") is not None, True)
check("newline-spanning snippet now grounds", ground("41.2 % 44.2 %", "41.2 %\n44.2 %") is not None, True)
check("all-whitespace snippet is refused", ground("real text here", "   "), None)


# --- 2. _number_in(): the claimed number must be in its own citation ---------
print("== _number_in() — the number-in-citation gate (finding #1) ==")

check("whole number present", _number_in("approximately 91 percent of net sales", 91), True)
check("float with decimal present", _number_in("gross margin of 41.2%", 41.2), True)
check("float given as 91.0 matches '91'", _number_in("91 percent", 91.0), True)
check("number absent is False", _number_in("150 employees worldwide", 50), False)
check("substring inside a bigger number is NOT a match", _number_in("revenue of 150", 50), False)
check("different decimal is NOT a match", _number_in("margin of 41.25%", 41.2), False)
check("None value is False", _number_in("anything at all", None), False)


# --- 3. the fix in action: mismatched number gets dropped --------------------
# This is the regression guard for finding #1 — the crack in the moat. A real,
# grounded quote paired with a number that ISN'T in it must NOT produce a finding.
print("== _ground_concentration / _ground_margin — number must back the quote ==")

conc_text = "we had one end customer, Apple Inc., that represented approximately 91 percent of total net sales."

# Honest case: number is in the quote -> finding stands.
good = _ground_concentration(conc_text, {
    "present": True, "customer": "Apple", "pct": 91,
    "snippet": "represented approximately 91 percent",
})
check("matching pct yields a finding", good is not None, True)
check("finding carries the grounded pct", good["pct"], 91)

# The moat test: real quote, WRONG number (50, not 91) -> dropped, not shown.
bad = _ground_concentration(conc_text, {
    "present": True, "customer": "Apple", "pct": 50,
    "snippet": "represented approximately 91 percent",
})
check("pct not in its own quote is DROPPED", bad, None)

# Guard still bites first: a fabricated quote is refused before we even check numbers.
check("fabricated quote refused", _ground_concentration(conc_text, {
    "present": True, "customer": "Samsung", "pct": 45,
    "snippet": "Samsung represented 45 percent",
}), None)

# Margin: both figures must be in the quote. One-cell quote (only 41.2) -> dropped.
margin_text = "Gross margin was 41.2 % in 2025 compared with 44.2 % in 2023."
half = _ground_margin(margin_text, {
    "present": True, "cur_pct": 41.2, "prev_pct": 44.2,
    "snippet": "41.2 %",  # quote contains cur but not prev
})
check("margin quote missing one figure is DROPPED", half, None)

whole = _ground_margin(margin_text, {
    "present": True, "cur_pct": 41.2, "prev_pct": 44.2,
    "snippet": "41.2 % in 2025 compared with 44.2 %",  # both figures present
})
check("margin quote with both figures stands", whole is not None, True)
check("margin concern flag set on a >1pt decline", whole["concern"], True)


# --- verdict ----------------------------------------------------------------
print(f"\nRESULT: {_passed} passed, {_failed} failed")
sys.exit(1 if _failed else 0)
