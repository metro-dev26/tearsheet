"""
checks.py — the diligence CHECKS (the proposers).

A check reads the filing and PROPOSES a finding: a human-readable claim plus the
exact snippet from the document that backs it. It then hands that snippet to the
grounding guard (ground.py). If the guard can't verify the snippet, the check
returns nothing — no grounding, no claim. Ever.

Today the detection is a plain regex. That's deliberate: keep the proposer simple
and get the guard + the propose/verify seam working end to end first. Later the
regex can be replaced by an LLM reading the filing — and NOTHING below the
`ground(...)` call has to change, because the guard already does the trusting-
nobody part.
"""

import re

from ground import ground

# Matches the single-customer concentration disclosure, e.g.:
#   "...we had one end customer, Apple Inc., who purchased through multiple
#    contract manufacturers and represented approximately 91 percent, 89 percent
#    and 87 percent of the Company's total net sales, respectively."
# We capture the customer name and the most recent (first) percentage. The whole
# matched span (match.group(0)) becomes the snippet we ask the guard to verify.
_CONCENTRATION_RE = re.compile(
    r"we had one end customer,\s*(?P<customer>[^,]+?),"
    r".*?represented approximately\s*(?P<pct>\d+)\s*percent"
    r".*?total net sales, respectively\.",
    re.IGNORECASE,
)


def check_customer_concentration(clean_text: str):
    """Propose a customer-concentration finding, grounded — or return None.

    A finding is:
      { check, claim, customer, pct, snippet, char_start, char_end }
    where claim is the human sentence (paraphrased, could be wrong) and the last
    three fields are the PROOF, produced only if the guard verified the snippet.
    """
    m = _CONCENTRATION_RE.search(clean_text)
    if not m:
        return None  # nothing to claim; stay silent

    customer = m.group("customer").strip()
    pct = int(m.group("pct"))
    snippet = m.group(0)  # exact substring of clean_text

    # The claim is a PARAPHRASE — a human sentence built from the extraction.
    # It is NOT trusted. Only the snippet is verified.
    claim = (
        f"Customer concentration risk: a single customer ({customer}) accounted "
        f"for approximately {pct}% of total net sales."
    )

    # Hand the raw snippet to the guard. No verification -> no finding.
    cite = ground(clean_text, snippet)
    if cite is None:
        return None

    return {
        "check": "customer_concentration",
        "claim": claim,
        "customer": customer,
        "pct": pct,
        **cite,  # snippet, char_start, char_end
    }


# Matches the year-over-year gross margin sentence, e.g.:
#   "Overall gross margin of 52.8 percent for fiscal year 2026 increased from
#    fiscal year 2025 gross margin of 52.5 percent."
# Captures the current-year margin, both years, the direction WORD as the filing
# states it, and the prior-year margin. group(0) is the snippet we verify.
_MARGIN_RE = re.compile(
    r"gross margin of\s*(?P<cur>\d+(?:\.\d+)?)\s*percent\s*for fiscal year\s*(?P<cur_yr>\d{4})"
    r"\s*(?P<direction>increased|decreased|remained flat|remained unchanged)"
    r"\s*from fiscal year\s*(?P<prev_yr>\d{4})\s*gross margin of\s*(?P<prev>\d+(?:\.\d+)?)\s*percent",
    re.IGNORECASE,
)

# How many percentage points of margin decline we treat as worth flagging as a
# concern (vs. just reporting the trend). A single number, easy to justify and
# tune. Below this, the trend is reported but not raised as a red flag.
_MARGIN_DECLINE_CONCERN_PTS = 1.0


def check_margin_trend(clean_text: str):
    """Propose a gross-margin-trend finding, grounded — or return None.

    Unlike the concentration check, this one reports the trend in BOTH directions
    and marks `concern=True` only when margin declined by more than the threshold.
    A diligence tool that stays silent on healthy margins but shouts on eroding
    ones is more useful than one that only ever flags.
    """
    m = _MARGIN_RE.search(clean_text)
    if not m:
        return None

    cur = float(m.group("cur"))
    prev = float(m.group("prev"))
    direction = m.group("direction").lower()
    delta = round(cur - prev, 2)  # positive = margin improved
    snippet = m.group(0)

    # A declining margin beyond the threshold is the actual red flag.
    concern = delta <= -_MARGIN_DECLINE_CONCERN_PTS

    claim = (
        f"Gross margin trend: {prev}% (FY{m.group('prev_yr')}) -> {cur}% "
        f"(FY{m.group('cur_yr')}), a {delta:+.1f} pt move ({direction})."
    )

    cite = ground(clean_text, snippet)
    if cite is None:
        return None

    return {
        "check": "margin_trend",
        "claim": claim,
        "cur_pct": cur,
        "prev_pct": prev,
        "delta_pts": delta,
        "direction": direction,
        "concern": concern,
        **cite,  # snippet, char_start, char_end
    }
