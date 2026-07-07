"""
run_diligence.py — run the checks against a filing and print grounded findings.

This wires the pieces together:
  parse_filing.parse  -> clean_text (+ offsets)
  checks.*            -> propose findings
  ground.ground       -> verify every claim, or drop it

It ends with a REFUSAL demo: we hand the guard a plausible-sounding but fake
snippet and watch it refuse. That refusal is the product. A tool that says
"I can't prove this, so I won't claim it" is worth more than one that always
has an answer.

Run (Git Bash):
    /c/Users/sujan/tearsheet/.venv/Scripts/python src/run_diligence.py
"""

from parse_filing import parse, latest_filing
from checks import check_customer_concentration, check_margin_trend
from ground import ground

# The registry of v1 checks. Every check has the same shape:
#   (clean_text) -> finding dict or None
# Adding a check later is just adding one entry here — the CLI and the Streamlit
# UI both drive off this single list, so neither can drift from the other.
CHECKS = [
    ("customer_concentration", check_customer_concentration),
    ("margin_trend", check_margin_trend),
]


def run_all_checks(clean_text: str) -> list:
    """Run every registered check against the filing text.

    Returns a list of (name, finding) pairs in registry order, where `finding`
    is the check's dict or None (not present / could not be grounded). Callers
    decide how to present a None — the CLI prints a line, the UI greys it out.
    """
    return [(name, run(clean_text)) for name, run in CHECKS]


def _show_context(clean_text: str, finding: dict, pad: int = 40) -> str:
    """Show the citation sitting in its surrounding text, so a human can eyeball
    that the offsets really point at the claimed words."""
    s, e = finding["char_start"], finding["char_end"]
    left = clean_text[max(0, s - pad):s]
    right = clean_text[e:e + pad]
    return f"...{left}[[{clean_text[s:e]}]]{right}..."


if __name__ == "__main__":
    src = latest_filing()
    print(f"Filing: {src.name}\n")

    clean_text, _chunks = parse(src)

    for name, finding in run_all_checks(clean_text):
        print(f"=== CHECK: {name} ===")
        if finding is None:
            print("No grounded finding (either not present, or could not be verified).")
        else:
            # A finding may carry a `concern` flag; surface it plainly.
            flag = ""
            if finding.get("concern") is True:
                flag = "  [CONCERN]"
            elif "concern" in finding:
                flag = "  [ok]"
            print(f"CLAIM:  {finding['claim']}{flag}")
            print(f"PROOF:  chars {finding['char_start']:,}-{finding['char_end']:,}")
            print(f"QUOTE:  \"{finding['snippet']}\"")
            print(f"IN CONTEXT: {_show_context(clean_text, finding)}")
        print()

    print("\n=== REFUSAL demo: the guard rejecting a fabricated claim ===")
    # A hallucinated snippet: reads plausibly, was never in the filing.
    fake = "we had one end customer, Samsung, representing 45 percent of net sales"
    result = ground(clean_text, fake)
    if result is None:
        print(f"REFUSED (ungrounded, claim dropped): \"{fake}\"")
    else:
        print("BUG: guard accepted a fabricated snippet -> " + str(result))
