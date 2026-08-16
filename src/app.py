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

Look & feel: the page is rendered as hand-authored HTML/CSS styled to read like
a printed EQUITY-RESEARCH NOTE — warm paper, serif headlines, hairline rules,
monospace reserved for the verbatim "receipts". Not stock Streamlit widgets, so
it doesn't look like every other Streamlit app. We pin streamlit==1.59.0, so the
custom CSS is stable.

Run (Git Bash):
    /c/Users/sujan/tearsheet/.venv/Scripts/streamlit run src/app.py
"""

import html
import json
import sys
from pathlib import Path

import streamlit as st

# Streamlit runs this script from wherever you launched it, so make sure src/
# is importable no matter what the working directory is.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ground import ground                        # noqa: E402  (import after path fix)
from parse_filing import FILINGS_DIR             # noqa: E402
import engine                                     # noqa: E402

GOLD_DIR = Path(__file__).resolve().parent.parent / "eval" / "gold"


@st.cache_data(show_spinner="Running diligence (cached)...")
def load(path_str: str):
    # The SAME engine the eval grades: parse + the LLM proposer behind the guard,
    # cached to eval/cache/ so the live page makes no network call once warm. This
    # is the fix for the demo previously running the dead Cirrus-tuned regex.
    clean_text, n_chunks, findings = engine.run(Path(path_str))
    return clean_text, n_chunks, findings


@st.cache_data
def gold_fakes_for(filing_name: str):
    """The fabricated claims to test the guard against, pulled from THIS filing's
    gold file (matched by its `filing` field, since Qorvo's filename and gold stem
    differ). Returns [] if there's no gold — the caller falls back to generic fakes.
    This kills the old Cirrus-hardcoded list that mislabeled other filings."""
    for gp in GOLD_DIR.glob("*.json"):
        try:
            g = json.loads(gp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if g.get("filing") == filing_name:
            return g.get("fabricated_claims", [])
    return []


def esc(x) -> str:
    """Escape every piece of filing text before it touches the HTML, so a stray
    < or & in a disclosure can never break the page."""
    return html.escape(str(x))


# ---------------------------------------------------------------------------
# Presentation helpers — DISPLAY ONLY, no diligence logic.
# ---------------------------------------------------------------------------
def fig_bits(f: dict):
    """The headline figure per check type: (number, subline, caption, color).
    A check the engine doesn't recognize returns None and renders no figure."""
    if f["check"] == "customer_concentration":
        return f'{f["pct"]}%', esc(f["customer"]), "share of net sales", "var(--ink-soft)"
    if f["check"] == "margin_trend":
        d = f["delta_pts"]
        # Flat (0.0 pt) is neither improvement nor decline — don't paint it green.
        if d > 0:
            arrow, color = "▲", "var(--ok)"
        elif d < 0:
            arrow, color = "▼", "var(--flag)"
        else:
            arrow, color = "→", "var(--muted)"
        return (f'{f["cur_pct"]}%', f'{arrow} {d:+.1f} pt YoY',
                f'gross margin, {esc(f["direction"])}', color)
    return None


def status_bits(f: dict):
    """concern=True -> Flag; concern=False -> No concern; no concern field ->
    Grounded. We never invent a verdict the engine didn't give."""
    if f.get("concern") is True:
        return "flag", "● Flag"
    if "concern" in f:
        return "ok", "No concern"
    return "ok", "Grounded"


def context_html(clean_text: str, f: dict, pad: int = 80) -> str:
    """The verified span in its real surrounding text, highlighted — the proof
    made visible, straight off the offsets the guard verified."""
    s, e = f["char_start"], f["char_end"]
    return (f"…{esc(clean_text[max(0, s - pad):s])}"
            f"<mark>{esc(clean_text[s:e])}</mark>"
            f"{esc(clean_text[e:e + pad])}…")


def finding_section(i: int, name: str, f: dict, clean_text: str) -> str:
    num = f"{i:02d}"
    pretty = esc(name.replace("_", " ").title())

    if f is None:
        return (
            '<section class="ts-find">'
            f'<div class="ts-find-head"><div class="ts-find-title">'
            f'<span class="ts-num">{num}</span>{pretty}</div>'
            '<div class="ts-flag muted">No claim</div></div>'
            '<p class="ts-claim" style="color:var(--muted)">No grounded finding — '
            'either not present in this filing, or the proposed claim could not be '
            'verified against the source text. Unverified claims are dropped, '
            'never shown.</p></section><hr class="ts-rule">'
        )

    st_cls, st_lbl = status_bits(f)
    fb = fig_bits(f)
    if fb:
        big, sub, cap, color = fb
        figure = (
            f'<div class="ts-fig"><div class="ts-fig-num">{esc(big)}</div>'
            f'<div class="ts-fig-sub" style="color:{color}">{sub}</div>'
            f'<div class="ts-fig-cap">{esc(cap)}</div></div>'
        )
        body_cls = "ts-find-body"
    else:
        figure = ""
        body_cls = "ts-find-body solo"

    s, e = f["char_start"], f["char_end"]
    return (
        '<section class="ts-find">'
        f'<div class="ts-find-head"><div class="ts-find-title">'
        f'<span class="ts-num">{num}</span>{pretty}</div>'
        f'<div class="ts-flag {st_cls}">{esc(st_lbl)}</div></div>'
        f'<div class="{body_cls}">{figure}<div class="ts-find-main">'
        f'<p class="ts-claim">{esc(f["claim"])}</p>'
        f'<div class="ts-qhead">Verbatim source — guard-verified</div>'
        f'<blockquote class="ts-quote">{esc(f["snippet"])}</blockquote>'
        f'<div class="ts-cite">Source: characters {s:,}–{e:,} · '
        f'<b>clean_text[start:end] is an exact string match.</b></div>'
        f'<details class="ts-details"><summary>Show surrounding filing text</summary>'
        f'<blockquote class="ts-quote">{context_html(clean_text, f)}</blockquote>'
        f'</details></div></div></section><hr class="ts-rule">'
    )


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Tearsheet — SEC 10-K diligence with receipts",
                   page_icon="📄", layout="centered")

CSS = """
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Source+Serif+4:ital,wght@0,400;0,600;0,700;1,400&display=swap');
:root{
  --paper:#f7f4ee;--paper2:#efeadf;--ink:#1c1a17;--ink-soft:#3c362d;
  --muted:#726a5c;--faint:#a8a091;--rule:#d9d3c6;
  --flag:#8a2b1e;--ok:#2f5d3a;--accent:#7a3b12;
  --serif:'Source Serif 4',Georgia,'Times New Roman',serif;
  --mono:'IBM Plex Mono','SF Mono',Menlo,Consolas,monospace;
}
.stApp{background:var(--paper);}
html,body,.stApp,[class*="css"]{font-family:var(--serif);color:var(--ink);}
[data-testid="stDecoration"]{display:none;}
[data-testid="stHeader"]{background:transparent;}
footer{display:none;}
.block-container{max-width:820px;padding-top:2.2rem;padding-bottom:5rem;}
.ts-runhead{display:flex;justify-content:space-between;flex-wrap:wrap;gap:.5rem;font:600 .72rem/1.4 var(--serif);letter-spacing:.18em;text-transform:uppercase;color:var(--muted);}
.ts-rule{border:none;border-top:1px solid var(--rule);margin:1.15rem 0;}
.ts-rule.thick{border-top:2px solid var(--ink);margin:.7rem 0 1.5rem;}
.ts-company{font:700 3.15rem/1.02 var(--serif);letter-spacing:-.015em;margin:.15rem 0 .55rem;}
.ts-meta{font:600 .78rem/1.5 var(--serif);letter-spacing:.13em;text-transform:uppercase;color:var(--muted);}
.ts-thesis{font:400 1.14rem/1.62 var(--serif);color:var(--ink-soft);margin:1.25rem 0 0;max-width:40rem;}
.ts-thesis b{font-weight:600;color:var(--ink);}
.ts-keyfigs{display:flex;flex-wrap:wrap;border-top:1px solid var(--ink);border-bottom:1px solid var(--ink);margin:2.1rem 0 2.8rem;}
.ts-kf{flex:1 1 0;min-width:118px;padding:1.05rem 1.3rem 1.05rem 0;}
.ts-kf-num{display:block;font:700 2.05rem/1 var(--serif);letter-spacing:-.01em;}
.ts-kf-num.ok{color:var(--ok);}
.ts-kf-lbl{display:block;font:600 .69rem/1.35 var(--serif);letter-spacing:.11em;text-transform:uppercase;color:var(--muted);margin-top:.5rem;}
.ts-sec-label{font:600 .74rem/1 var(--serif);letter-spacing:.18em;text-transform:uppercase;color:var(--muted);margin:0 0 1.5rem;}
.ts-find{margin:0;}
.ts-find-head{display:flex;justify-content:space-between;align-items:baseline;gap:1rem;margin-bottom:1.05rem;}
.ts-find-title{font:600 1.42rem/1.2 var(--serif);letter-spacing:-.01em;display:flex;gap:.75rem;align-items:baseline;}
.ts-num{font:600 .92rem/1 var(--serif);color:var(--flag);letter-spacing:.04em;}
.ts-flag{font:600 .71rem/1 var(--serif);letter-spacing:.11em;text-transform:uppercase;white-space:nowrap;}
.ts-flag.flag{color:var(--flag);}
.ts-flag.ok{color:var(--ok);}
.ts-flag.muted{color:var(--faint);}
.ts-find-body{display:grid;grid-template-columns:148px 1fr;gap:1.9rem;}
.ts-find-body.solo{grid-template-columns:1fr;}
@media(max-width:600px){.ts-find-body{grid-template-columns:1fr;gap:1.1rem;}}
.ts-fig-num{font:700 2.95rem/1 var(--serif);letter-spacing:-.025em;}
.ts-fig-sub{font:600 .96rem/1.3 var(--serif);margin-top:.38rem;}
.ts-fig-cap{font:400 .82rem/1.4 var(--serif);color:var(--muted);margin-top:.3rem;}
.ts-claim{font:400 1.06rem/1.62 var(--serif);margin:0 0 1.15rem;}
.ts-qhead{font:600 .67rem/1 var(--serif);letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin-bottom:.55rem;}
.ts-quote{font:400 .84rem/1.72 var(--mono);color:var(--ink);background:rgba(28,26,23,.035);border-left:2px solid var(--ink);padding:.72rem .98rem;margin:0;white-space:pre-wrap;word-break:break-word;}
.ts-cite{font:italic 400 .84rem/1.55 var(--serif);color:var(--muted);margin-top:.58rem;}
.ts-cite b{font-style:normal;font-weight:600;color:var(--ok);}
details.ts-details{margin-top:.75rem;}
details.ts-details summary{font:600 .82rem/1 var(--serif);color:var(--accent);cursor:pointer;list-style:none;display:inline-flex;gap:.45rem;align-items:center;}
details.ts-details summary::-webkit-details-marker{display:none;}
details.ts-details summary::before{content:"+";font:600 1rem/1 var(--serif);}
details.ts-details[open] summary::before{content:"–";}
details.ts-details .ts-quote{margin-top:.6rem;border-left-color:var(--rule);}
mark{background:#f0e2b0;color:var(--ink);padding:.05em .16em;}
.ts-note{font:400 1.04rem/1.62 var(--serif);color:var(--ink-soft);margin:0 0 1.5rem;max-width:40rem;}
.ts-note b{font-weight:600;color:var(--ink);}
.ts-refuse-list{list-style:none;margin:0;padding:0;}
.ts-refuse{padding:.95rem 0;border-top:1px solid var(--rule);}
.ts-refuse:first-child{border-top:none;}
.ts-refuse-claim{font:400 .85rem/1.6 var(--mono);color:var(--muted);}
.ts-para{font:italic 600 .78rem/1 var(--serif);color:var(--flag);margin-left:.55rem;}
.ts-refuse-verdict{font:600 .95rem/1.45 var(--serif);color:var(--ok);margin-top:.5rem;}
.ts-refuse-verdict .x{color:var(--flag);font-weight:700;margin-right:.42rem;}
.ts-refuse-verdict .why{font-weight:400;color:var(--ink-soft);}
.ts-refuse-verdict.bug{color:var(--flag);}
.ts-refuse-sum{font:400 1.05rem/1.62 var(--serif);margin-top:1.5rem;padding-top:1.15rem;border-top:2px solid var(--ink);}
.ts-refuse-sum b{font-weight:700;}
.ts-colophon{margin-top:3rem;padding-top:1.25rem;border-top:1px solid var(--rule);font:400 .82rem/1.75 var(--serif);color:var(--muted);}
.ts-colophon a{color:var(--accent);text-decoration:none;}
.ts-colophon a:hover{text-decoration:underline;}
"""
st.markdown("<style>" + CSS + "</style>", unsafe_allow_html=True)

# --- pick the filing -------------------------------------------------------
# A selector, so the demo can SHOW generality across companies instead of silently
# defaulting to whichever filename sorts last (which used to serve Skyworks to the
# Cirrus-only regex and render a wall of "No claim").
filings = sorted(FILINGS_DIR.glob("*.htm"))
if not filings:
    st.error(f"No filings in {FILINGS_DIR}. Run fetch_filing.py first.")
    st.stop()

names = [f.name for f in filings]
default_idx = next((i for i, n in enumerate(names) if n.upper().startswith("CIRRUS")), 0)
choice = st.selectbox("Filing", names, index=default_idx)
filing_path = FILINGS_DIR / choice

# The SAME engine the eval grades (parse + LLM proposer + guard), cached to disk.
# A filing with no cache needs a live model call, which can fail (e.g. free-tier
# quota). Fail with a message, not a stack trace — the demo must never explode.
try:
    clean_text, n_chunks, findings = load(str(filing_path))
except Exception as exc:  # noqa: BLE001 — surface any engine/network failure cleanly
    st.error(
        f"Couldn't run diligence on {choice}: {exc}\n\n"
        "This filing likely isn't cached yet and the live model call failed. "
        "Pick a cached filing, or rebuild the cache with:  "
        "python src/run_eval.py --refresh"
    )
    st.stop()
results = list(findings.items())
n_grounded = sum(1 for _, f in results if f is not None)

# --- fabricated claims the guard must refuse --------------------------------
# Pulled from THIS filing's own gold file (never another company's claims), plus a
# paraphrase built LIVE from the real concentration finding — right in meaning,
# different in words — which the guard must still refuse. Generic, filing-agnostic
# fakes are the fallback when a filing has no gold yet.
fake_items = []  # (claim_text, is_paraphrase)
_gold_fakes = gold_fakes_for(filing_path.name)
if _gold_fakes:
    fake_items += [(s, False) for s in _gold_fakes]
else:
    fake_items += [
        ("the Company reported no material customer concentration risk", False),
        ("gross margin collapsed to 5.0 percent this fiscal year", False),
    ]

_conc = findings.get("customer_concentration")
if _conc is not None:
    _para = (f"our largest customer, {_conc.get('customer')}, accounted for "
             f"{_conc.get('pct')}% of the company's revenue")
    # Only count it as a fake if it genuinely is NOT verbatim in the filing.
    if ground(clean_text, _para) is None:
        fake_items.append((_para, True))

refusals = [(snip, para, ground(clean_text, snip) is None) for snip, para in fake_items]
n_refused = sum(1 for *_, refused in refusals if refused)
n_fakes = len(fake_items)

# --- filing identity, derived from the filename (stays company-agnostic) ---
parts = filing_path.stem.split("_")
company = parts[0].title() if parts else filing_path.stem
fdate = parts[1] if len(parts) > 1 else ""
fform = parts[2] if len(parts) > 2 else "10-K"

# --- masthead + thesis -----------------------------------------------------
meta = f'Form {esc(fform)}'
if fdate:
    meta += f' · Filed {esc(fdate)}'
meta += f' · {n_chunks:,} traceable chunks'

st.markdown(
    '<div class="ts-runhead"><span>Tearsheet · Automated SEC Diligence</span>'
    '<span>With receipts</span></div>'
    '<hr class="ts-rule thick">'
    f'<div class="ts-company">{esc(company)}</div>'
    f'<div class="ts-meta">{meta}</div>'
    '<p class="ts-thesis">Automated first-pass diligence on a company\'s SEC '
    '10-K. Every finding is <b>citation-linked to the exact characters in the '
    'filing</b>, and any claim that can\'t be traced to the source is dropped. '
    'No verified source, no claim.</p>',
    unsafe_allow_html=True,
)

# --- key figures -----------------------------------------------------------
figs = [
    (str(len(results)), "Checks run", ""),
    (str(n_grounded), "Grounded findings", "ok"),
    (f"{n_refused}/{n_fakes}", "Fabricated claims refused", "ok"),
    (f"{len(clean_text) // 1000}K", "Chars parsed", ""),
]
kf = "".join(
    f'<div class="ts-kf"><span class="ts-kf-num {cl}">{esc(n)}</span>'
    f'<span class="ts-kf-lbl">{esc(l)}</span></div>'
    for n, l, cl in figs
)
st.markdown(f'<div class="ts-keyfigs">{kf}</div>', unsafe_allow_html=True)

# --- findings --------------------------------------------------------------
sections = "".join(
    finding_section(i, name, f, clean_text)
    for i, (name, f) in enumerate(results, 1)
)
st.markdown(
    '<div class="ts-sec-label">Diligence findings</div>' + sections,
    unsafe_allow_html=True,
)

# --- the grounding guard: the hero of the product --------------------------
refuse_items = ""
for snip, para, refused in refusals:
    tag = '<span class="ts-para">paraphrase of the real finding</span>' if para else ""
    if refused:
        verdict = ('<div class="ts-refuse-verdict"><span class="x">✕</span>'
                   'Refused — not found verbatim, so dropped.</div>')
    else:
        # Should be impossible. If it happens, say so loudly, don't hide it.
        verdict = ('<div class="ts-refuse-verdict bug"><span class="x">!</span>'
                   'BUG: the guard accepted a fabricated snippet.</div>')
    refuse_items += (
        f'<li class="ts-refuse"><div class="ts-refuse-claim">“{esc(snip)}”{tag}</div>'
        f'{verdict}</li>'
    )

st.markdown(
    '<div class="ts-sec-label">The grounding guard — watch it refuse</div>'
    '<p class="ts-note">Language models hallucinate plausible-sounding financial '
    'facts. Tearsheet\'s guard is <b>deterministic on purpose</b>: a claim '
    'survives only if its exact words physically exist in the filing. Below are '
    'fabricated disclosures — including a paraphrase of this filing\'s genuine '
    'finding — each one refused.</p>'
    f'<ol class="ts-refuse-list">{refuse_items}</ol>'
    f'<p class="ts-refuse-sum"><b>{n_refused} of {n_fakes} fabricated '
    'claims refused.</b> Refusing is the point: “I can’t prove it, so I won’t '
    'say it.”</p>',
    unsafe_allow_html=True,
)

# --- colophon --------------------------------------------------------------
st.markdown(
    '<div class="ts-colophon">Prepared by <b>Tearsheet</b> · Python · Streamlit · '
    'BeautifulSoup over SEC EDGAR filings. An LLM proposes claims by reading for '
    'meaning; the deterministic grounding guard verifies every quote — and every '
    'number inside it — against the source, and drops anything it can\'t prove. '
    '&nbsp;·&nbsp; '
    '<a href="https://github.com/metro-dev26/tearsheet" target="_blank">'
    'Source on GitHub →</a></div>',
    unsafe_allow_html=True,
)
