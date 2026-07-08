"""
app.py — the Streamlit front end for Tearsheet. The DEMO SURFACE.

What this file is (and is not):
This is a THIN WINDOW onto the engine you already built. It contains ZERO
diligence logic. It imports the same parse / checks / ground functions the CLI
uses and only decides how to DISPLAY their output. That's deliberate:

    parse_filing.parse   -> clean_text (+ verified offsets)
    run_diligence.CHECKS -> the single registry of checks (the engine's menu)
    run_diligence.run_all_checks -> runs them all
    ground.ground        -> the guard (used here only for the refusal demo)

Because both the CLI and this app drive off the SAME `CHECKS` registry, adding
a check to the engine automatically shows up in both — the two can never drift
apart. If you ever find yourself writing an `if company == ...` or a regex in
this file, stop: that logic belongs in checks.py, behind the guard.

Run (Git Bash):
    /c/Users/sujan/tearsheet/.venv/Scripts/streamlit run src/app.py
"""

import sys
from pathlib import Path

import streamlit as st

# Streamlit runs this script from wherever you launched it, so make sure src/
# is importable no matter what the working directory is. (The CLI doesn't need
# this because you run it as `python src/run_diligence.py` and Python puts the
# script's own folder on the path — Streamlit is the odd one out.)
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ground import ground                       # noqa: E402  (import after path fix)
from parse_filing import latest_filing, parse   # noqa: E402
from run_diligence import run_all_checks        # noqa: E402


# ---------------------------------------------------------------------------
# Load + parse the filing — cached.
#
# Parsing a 1.7 MB 10-K takes a few seconds. Streamlit reruns this whole script
# top-to-bottom on EVERY interaction (that's its execution model), so without
# caching we'd re-parse the filing every time you click anything. @st.cache_data
# memoizes on the function's arguments: same filing path -> instant cached result.
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Parsing filing...")
def load_filing(path_str: str):
    clean_text, chunks = parse(Path(path_str))
    return clean_text, len(chunks)


def context_view(clean_text: str, finding: dict, pad: int = 40) -> str:
    """The citation sitting in its surrounding text (same idea as the CLI's
    _show_context): pad characters of real filing text on each side, with the
    verified span marked by [[ ]]. Lets a human eyeball that the offsets truly
    point at the claimed words — the proof, made visible."""
    s, e = finding["char_start"], finding["char_end"]
    left = clean_text[max(0, s - pad):s]
    right = clean_text[e:e + pad]
    return f"...{left}[[{clean_text[s:e]}]]{right}..."


def badge(finding: dict) -> str:
    """Mirror the CLI's flag logic exactly (run_diligence.py):
    concern=True -> CONCERN (red), concern=False -> ok (green), and if the
    check doesn't set `concern` at all -> a neutral GROUNDED badge. We do NOT
    invent a verdict the engine didn't give."""
    if finding.get("concern") is True:
        return ":red-background[**CONCERN**]"
    if "concern" in finding:
        return ":green-background[**ok**]"
    return ":gray-background[**GROUNDED**]"


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Tearsheet — SEC 10-K diligence with receipts",
                   page_icon="📄", layout="wide")

# A LITTLE presentation CSS. Kept minimal and targeting only stable containers:
# cap the content width so text isn't stretched across an ultrawide monitor
# (the default wide layout looked sparse), and give the page some top breathing
# room. Everything visual beyond this lives in .streamlit/config.toml, which is
# the version-proof way to theme Streamlit.
st.markdown(
    """
    <style>
      .block-container { max-width: 1080px; padding-top: 3rem; padding-bottom: 4rem; }
      [data-testid="stMetricValue"] { font-size: 1.9rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- header: eyebrow + title + one-line positioning ------------------------
st.markdown(
    "<div style='letter-spacing:.14em;font-size:.72rem;font-weight:600;"
    "color:#4f8cff;text-transform:uppercase;margin-bottom:.2rem;'>"
    "SEC 10-K diligence · with receipts</div>",
    unsafe_allow_html=True,
)
st.title("📄 Tearsheet")
st.markdown(
    "Reads a company's SEC 10-K and flags what a diligence analyst would care "
    "about — and **every claim is citation-linked to the exact characters in "
    "the filing**. No verified source, no claim."
)

# --- which filing are we looking at ---------------------------------------
try:
    filing_path = latest_filing()
except FileNotFoundError as e:
    # No downloaded filing = nothing to analyze. Say so plainly and stop —
    # never render an empty dashboard that looks like "no risks found".
    st.error(f"No filing found: {e}")
    st.stop()

clean_text, n_chunks = load_filing(str(filing_path))

# Run the whole engine ONCE, up front, so both the summary tiles and the
# detailed cards below read from the same results (no double work, no drift).
results = list(run_all_checks(clean_text))
n_grounded = sum(1 for _, f in results if f is not None)

# The fabricated claims the guard must refuse. These MIRROR eval/gold/*.json —
# same set the automated eval grades against — including a paraphrase of the
# REAL disclosure (same meaning, different words), which is exactly how an LLM
# proposer fails. We run them through the guard live, below.
FABRICATED = [
    ("we had one end customer, Samsung, representing 45 percent of net sales",
     "Wrong customer, wrong number — pure invention."),
    ("our largest customer, Apple Inc., accounted for 91% of our revenue",
     "A PARAPHRASE of the real disclosure: correct in meaning, not verbatim. "
     "The guard still refuses it — meaning is not proof."),
    ("gross margin of 48.2 percent for fiscal year 2026 decreased from fiscal "
     "year 2025 gross margin of 52.5 percent",
     "Right shape, fabricated numbers."),
    ("the Company is substantially dependent on a single customer for the "
     "majority of its sales",
     "True in spirit, absent from the text as written."),
]
n_refused = sum(1 for snippet, _ in FABRICATED if ground(clean_text, snippet) is None)

st.caption(
    f"Filing: `{filing_path.name}` · {len(clean_text):,} characters of "
    f"disclosure text · {n_chunks:,} traceable chunks"
)

# --- summary tiles: the state of the analysis at a glance ------------------
t1, t2, t3, t4 = st.columns(4)
t1.metric("Checks run", len(results))
t2.metric("Grounded findings", n_grounded)
t3.metric("Fabricated claims refused", f"{n_refused}/{len(FABRICATED)}")
t4.metric("Disclosure parsed", f"{len(clean_text) // 1000}K chars")

st.divider()

# ---------------------------------------------------------------------------
# Findings — one card per registered check, in registry order.
# run_all_checks returns (name, finding-or-None) pairs; the engine already did
# the proposing AND the verifying. All we do here is present.
# ---------------------------------------------------------------------------
st.header("Diligence findings")


def headline_metric(finding: dict) -> None:
    """DISPLAY ONLY: the one number a reader should see first, as a metric tile.
    This is presentation formatting, not diligence logic — a check the engine
    doesn't recognize simply gets no tile and still renders its claim + proof."""
    if finding["check"] == "customer_concentration":
        st.metric(f"{finding['customer']} — share of net sales", f"{finding['pct']}%")
    elif finding["check"] == "margin_trend":
        st.metric(
            f"Gross margin ({finding['direction']})",
            f"{finding['cur_pct']}%",
            delta=f"{finding['delta_pts']:+.1f} pt YoY",
        )


for name, finding in results:
    pretty = name.replace("_", " ").title()

    if finding is None:
        # The check found nothing it could PROVE. Greyed out, not hidden —
        # "we looked and won't claim anything" is information too.
        with st.container(border=True):
            st.subheader(pretty)
            st.caption(
                "No grounded finding — either not present in this filing, or "
                "the claim could not be verified against the source text "
                "(unverified claims are dropped, never shown)."
            )
        continue

    with st.container(border=True):
        st.subheader(f"{pretty} {badge(finding)}")

        # Left: the headline number. Right: the claim + the proof behind it.
        metric_col, detail_col = st.columns([1, 2.4])
        with metric_col:
            headline_metric(finding)
        with detail_col:
            # The CLAIM — a human paraphrase built by the check. Readable, but
            # never trusted on its own...
            st.markdown(f"**Claim:** {finding['claim']}")

            # ...because THIS is what makes it trustworthy: the verbatim words
            # from the filing, and exactly where they live.
            st.markdown("**Verbatim source quote** (verified by the grounding guard):")
            st.code(finding["snippet"], language=None, wrap_lines=True)
            st.caption(
                f"Proof: characters {finding['char_start']:,}–{finding['char_end']:,} "
                f"of the parsed filing. `clean_text[start:end]` equals the quote "
                f"above, character for character."
            )

            # The quote in its natural habitat, so you can see it isn't cropped
            # out of context. Hidden behind an expander to keep the card compact.
            with st.expander("See the quote in surrounding filing text"):
                st.code(context_view(clean_text, finding), language=None, wrap_lines=True)

st.divider()

# ---------------------------------------------------------------------------
# THE REFUSAL DEMO — the hero of the product.
#
# Anyone can build a tool that always has an answer. Tearsheet's differentiator
# is that it REFUSES to make a claim it cannot physically locate in the filing.
# We hand the guard four fabricated-but-plausible disclosures and show each one
# getting dropped. Same guard, same function, no special casing — the same set
# the automated eval grades against.
# ---------------------------------------------------------------------------
st.header("🛡️ The grounding guard — watch it refuse")
st.markdown(
    "LLMs hallucinate plausible-sounding financial facts. Tearsheet's guard is "
    "**dumb and deterministic on purpose**: a claim only survives if its exact "
    "words physically exist in the filing. Below are four fabricated disclosures "
    "that *sound* real — including a paraphrase of the genuine finding. The guard "
    "refuses every one."
)

for snippet, why in FABRICATED:
    with st.container(border=True):
        st.code(snippet, language=None, wrap_lines=True)
        if ground(clean_text, snippet) is None:
            st.markdown(f":green[**REFUSED — dropped.**] {why}")
        else:
            # This should be impossible. If it ever happens, the guard is broken
            # and we say so loudly instead of pretending everything is fine.
            st.error(f"BUG: the guard accepted a fabricated snippet: {snippet!r}")

st.success(
    f"**{n_refused} of {len(FABRICATED)} fabricated claims refused.** "
    "Refusing is the feature: *\"I can't prove it, so I won't say it.\"*"
)
