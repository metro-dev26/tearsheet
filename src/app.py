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

The whole page is rendered as hand-authored HTML/CSS rather than out of stock
Streamlit widgets. That's on purpose: Streamlit's default components make every
app look the same. We pin streamlit==1.59.0, so this custom CSS is stable.

Run (Git Bash):
    /c/Users/sujan/tearsheet/.venv/Scripts/streamlit run src/app.py
"""

import html
import sys
from pathlib import Path

import streamlit as st

# Streamlit runs this script from wherever you launched it, so make sure src/
# is importable no matter what the working directory is.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ground import ground                       # noqa: E402  (import after path fix)
from parse_filing import latest_filing, parse   # noqa: E402
from run_diligence import run_all_checks        # noqa: E402


# ---------------------------------------------------------------------------
# Load + parse the filing — cached. Parsing a 1.7 MB 10-K takes a few seconds
# and Streamlit reruns the whole script on every interaction, so we memoize.
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Parsing filing...")
def load_filing(path_str: str):
    clean_text, chunks = parse(Path(path_str))
    return clean_text, len(chunks)


def esc(x) -> str:
    """Every piece of filing text is escaped before it touches the HTML, so a
    stray < or & in a disclosure can never break the page."""
    return html.escape(str(x))


# ---------------------------------------------------------------------------
# Presentation helpers. DISPLAY ONLY — no diligence logic lives here.
# ---------------------------------------------------------------------------
def metric_bits(f: dict):
    """The one headline number a reader should see first, per check type.
    A check the engine doesn't recognize returns None and simply renders no
    metric — its claim + proof still show."""
    if f["check"] == "customer_concentration":
        return f'{f["pct"]}%', esc(f["customer"]), "share of net sales", "var(--accent)"
    if f["check"] == "margin_trend":
        d = f["delta_pts"]
        arrow = "▲" if d >= 0 else "▼"
        color = "var(--green)" if d >= 0 else "var(--red)"
        return (f'{f["cur_pct"]}%', f'{arrow} {d:+.1f} pt YoY',
                f'gross margin · {esc(f["direction"])}', color)
    return None


def status_bits(f: dict):
    """concern=True -> red Concern; concern=False -> green OK; no concern field
    -> neutral Grounded. We never invent a verdict the engine didn't give."""
    if f.get("concern") is True:
        return "concern", "Concern"
    if "concern" in f:
        return "ok", "OK"
    return "ok", "Grounded"


def context_html(clean_text: str, f: dict, pad: int = 70) -> str:
    """The verified span sitting in its real surrounding text, highlighted — the
    proof, made visible. Reads straight off the offsets the guard verified."""
    s, e = f["char_start"], f["char_end"]
    left = esc(clean_text[max(0, s - pad):s])
    mid = esc(clean_text[s:e])
    right = esc(clean_text[e:e + pad])
    return f"…{left}<mark>{mid}</mark>{right}…"


def finding_card(name: str, f: dict, clean_text: str) -> str:
    pretty = esc(name.replace("_", " ").title())

    if f is None:
        return (
            '<div class="ts-card">'
            f'<div class="ts-card-head"><div class="ts-card-name">{pretty}</div>'
            '<div class="ts-status muted">No claim</div></div>'
            '<div class="ts-claim muted">No grounded finding — either not present '
            'in this filing, or the proposed claim could not be verified against '
            'the source text. Unverified claims are dropped, never shown.</div></div>'
        )

    st_cls, st_lbl = status_bits(f)
    card_cls = "ts-card concern" if f.get("concern") is True else "ts-card"

    mb = metric_bits(f)
    if mb:
        big, sub, lbl, sub_color = mb
        metric = (
            f'<div class="ts-metric"><div class="ts-metric-num">{esc(big)}</div>'
            f'<div class="ts-metric-sub" style="color:{sub_color}">{sub}</div>'
            f'<div class="ts-metric-lbl">{esc(lbl)}</div></div>'
        )
        body_cls = "ts-body"
    else:
        metric = ""
        body_cls = "ts-body solo"

    s, e = f["char_start"], f["char_end"]
    return (
        f'<div class="{card_cls}">'
        f'<div class="ts-card-head"><div class="ts-card-name">{pretty}</div>'
        f'<div class="ts-status {st_cls}">{esc(st_lbl)}</div></div>'
        f'<div class="{body_cls}">{metric}<div class="ts-detail">'
        f'<div class="ts-claim"><b>Claim.</b> {esc(f["claim"])}</div>'
        f'<div class="ts-qlabel">Verbatim source quote · guard-verified</div>'
        f'<div class="ts-quote">{esc(f["snippet"])}</div>'
        f'<div class="ts-proof">⌖ chars {s:,}–{e:,}'
        f'<span>· clean_text[start:end] matches character-for-character</span></div>'
        f'<details class="ts-details"><summary>See the quote in surrounding filing text</summary>'
        f'<div class="ts-quote">{context_html(clean_text, f)}</div></details>'
        f'</div></div></div>'
    )


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Tearsheet — SEC 10-K diligence with receipts",
                   page_icon="📄", layout="centered")

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');
:root{
  --bg:#0b0e14;--surface:#12161f;--surface2:#1a1f2b;--border:#232a37;--border-soft:#1c2230;
  --text:#e6edf3;--muted:#8b97a8;--faint:#5b6675;
  --accent:#4f8cff;--green:#3fb950;--red:#f85149;--amber:#d29922;
  --mono:'JetBrains Mono','SF Mono',Menlo,Consolas,monospace;
  --sans:'Inter',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
}
.stApp{background:radial-gradient(1100px 560px at 50% -8%, #141c2b 0%, var(--bg) 55%);}
html,body,.stApp,[class*="css"]{font-family:var(--sans);color:var(--text);}
[data-testid="stDecoration"]{display:none;}
[data-testid="stHeader"]{background:transparent;}
footer{display:none;}
.block-container{max-width:900px;padding-top:2.2rem;padding-bottom:5rem;}
.ts-eyebrow{font:600 .72rem/1 var(--sans);letter-spacing:.18em;text-transform:uppercase;color:var(--accent);margin-bottom:1.1rem;display:flex;gap:.6rem;align-items:center;}
.ts-eyebrow::before{content:"";width:24px;height:2px;background:var(--accent);border-radius:2px;}
.ts-title{font:800 3rem/1.04 var(--sans);letter-spacing:-.025em;margin:.1rem 0 .7rem;background:linear-gradient(180deg,#ffffff,#aeb9c9);-webkit-background-clip:text;background-clip:text;color:transparent;}
.ts-tagline{font:400 1.06rem/1.6 var(--sans);color:var(--muted);max-width:44rem;}
.ts-tagline b{color:var(--text);font-weight:600;}
.ts-stats{display:flex;flex-wrap:wrap;margin:2.1rem 0 1.3rem;border:1px solid var(--border);border-radius:16px;background:linear-gradient(180deg,var(--surface),#0e131c);overflow:hidden;}
.ts-stat{flex:1 1 0;min-width:132px;padding:1.15rem 1.35rem;border-right:1px solid var(--border-soft);}
.ts-stat:last-child{border-right:none;}
.ts-stat-num{font:700 1.8rem/1 var(--sans);letter-spacing:-.01em;color:var(--text);}
.ts-stat-num.green{color:var(--green);}
.ts-stat-lbl{font:500 .73rem/1.3 var(--sans);color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-top:.5rem;}
.ts-filingbar{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;margin:0 0 2.6rem;}
.ts-pill{font:500 .8rem/1 var(--sans);color:var(--muted);background:var(--surface);border:1px solid var(--border);padding:.44rem .72rem;border-radius:999px;}
.ts-pill b{color:var(--text);font-weight:600;}
.ts-sec{font:700 .78rem/1 var(--sans);letter-spacing:.14em;text-transform:uppercase;color:var(--faint);margin:2.7rem 0 1.15rem;display:flex;align-items:center;gap:.6rem;}
.ts-sec::after{content:"";flex:1;height:1px;background:var(--border);}
.ts-card{position:relative;border:1px solid var(--border);border-radius:16px;background:var(--surface);padding:1.5rem 1.6rem 1.35rem;margin-bottom:1.05rem;overflow:hidden;}
.ts-card::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--green);}
.ts-card.concern::before{background:var(--red);}
.ts-card-head{display:flex;justify-content:space-between;align-items:center;gap:1rem;margin-bottom:1.15rem;}
.ts-card-name{font:700 1.08rem/1.2 var(--sans);letter-spacing:-.01em;color:var(--text);}
.ts-status{font:600 .7rem/1 var(--sans);letter-spacing:.06em;text-transform:uppercase;padding:.36rem .62rem;border-radius:8px;display:inline-flex;align-items:center;gap:.42rem;}
.ts-status.ok{color:var(--green);background:rgba(63,185,80,.12);border:1px solid rgba(63,185,80,.25);}
.ts-status.concern{color:var(--red);background:rgba(248,81,73,.12);border:1px solid rgba(248,81,73,.25);}
.ts-status.muted{color:var(--faint);background:rgba(139,151,168,.08);border:1px solid var(--border);}
.ts-status.ok::before,.ts-status.concern::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor;}
.ts-body{display:grid;grid-template-columns:168px 1fr;gap:1.7rem;}
.ts-body.solo{grid-template-columns:1fr;}
@media(max-width:620px){.ts-body{grid-template-columns:1fr;gap:1.1rem;}}
.ts-metric-num{font:800 2.7rem/1 var(--sans);letter-spacing:-.035em;color:var(--text);}
.ts-metric-sub{font:600 .96rem/1.3 var(--sans);margin-top:.42rem;}
.ts-metric-lbl{font:500 .77rem/1.35 var(--sans);color:var(--muted);margin-top:.28rem;text-transform:uppercase;letter-spacing:.04em;}
.ts-claim{font:400 .99rem/1.55 var(--sans);color:var(--text);margin-bottom:1.05rem;}
.ts-claim.muted{color:var(--muted);margin-bottom:0;}
.ts-claim b{font-weight:600;color:var(--accent);}
.ts-qlabel{font:600 .7rem/1 var(--sans);letter-spacing:.07em;text-transform:uppercase;color:var(--faint);margin-bottom:.55rem;}
.ts-quote{font:400 .87rem/1.65 var(--mono);color:#c9d4e2;background:#0a0e15;border:1px solid var(--border);border-radius:10px;padding:.85rem 1rem;white-space:pre-wrap;word-break:break-word;}
.ts-proof{font:500 .78rem/1.5 var(--mono);color:var(--green);margin-top:.62rem;display:flex;align-items:baseline;gap:.5rem;flex-wrap:wrap;}
.ts-proof span{color:var(--muted);}
details.ts-details{margin-top:.85rem;}
details.ts-details summary{font:500 .82rem/1 var(--sans);color:var(--accent);cursor:pointer;list-style:none;display:inline-flex;align-items:center;gap:.45rem;}
details.ts-details summary::-webkit-details-marker{display:none;}
details.ts-details summary::before{content:"▸";transition:transform .15s;}
details.ts-details[open] summary::before{transform:rotate(90deg);}
details.ts-details .ts-quote{margin-top:.7rem;}
mark{background:rgba(79,140,255,.24);color:#e2ebff;border-radius:3px;padding:.06em .18em;}
.ts-refuse{border:1px solid var(--border);border-left:3px solid var(--amber);border-radius:12px;background:var(--surface);padding:1rem 1.2rem;margin-bottom:.75rem;}
.ts-refuse.para{border-left-color:var(--accent);}
.ts-refuse-claim{font:400 .86rem/1.5 var(--mono);color:var(--muted);}
.ts-tag{font:600 .64rem/1 var(--sans);text-transform:uppercase;letter-spacing:.08em;color:var(--accent);background:rgba(79,140,255,.12);border:1px solid rgba(79,140,255,.25);padding:.26rem .46rem;border-radius:6px;margin-left:.55rem;white-space:nowrap;}
.ts-verdict{font:600 .85rem/1.4 var(--sans);color:var(--green);margin-top:.62rem;}
.ts-verdict .x{color:var(--red);font-weight:800;margin-right:.35rem;}
.ts-verdict .why{color:var(--muted);font-weight:400;}
.ts-verdict.bug{color:var(--red);}
.ts-summary{border:1px solid rgba(63,185,80,.28);background:rgba(63,185,80,.08);border-radius:12px;padding:1.05rem 1.25rem;font:500 .96rem/1.5 var(--sans);color:var(--text);margin-top:.35rem;}
.ts-summary b{color:var(--green);font-weight:700;}
.ts-foot{margin-top:3.6rem;padding-top:1.7rem;border-top:1px solid var(--border);font:400 .82rem/1.7 var(--sans);color:var(--faint);}
.ts-foot a{color:var(--accent);text-decoration:none;}
.ts-foot a:hover{text-decoration:underline;}
.ts-foot b{color:var(--muted);font-weight:600;}
"""
st.markdown("<style>" + CSS + "</style>", unsafe_allow_html=True)

# --- load the filing -------------------------------------------------------
try:
    filing_path = latest_filing()
except FileNotFoundError as e:
    st.error(f"No filing found: {e}")
    st.stop()

clean_text, n_chunks = load_filing(str(filing_path))

# Run the whole engine ONCE; the tiles and the cards read the same results.
results = list(run_all_checks(clean_text))
n_grounded = sum(1 for _, f in results if f is not None)

# The fabricated claims the guard must refuse. These MIRROR eval/gold/*.json —
# the same set the automated eval grades against — including a paraphrase of the
# REAL disclosure (index 1): correct in meaning, not verbatim. The guard refuses
# it anyway, because meaning is not proof.
FABRICATED = [
    ("we had one end customer, Samsung, representing 45 percent of net sales",
     "Wrong customer, wrong number — pure invention.", False),
    ("our largest customer, Apple Inc., accounted for 91% of our revenue",
     "A paraphrase of the real disclosure: right in meaning, not verbatim.", True),
    ("gross margin of 48.2 percent for fiscal year 2026 decreased from fiscal "
     "year 2025 gross margin of 52.5 percent",
     "Right shape, fabricated numbers.", False),
    ("the Company is substantially dependent on a single customer for the "
     "majority of its sales",
     "True in spirit, absent from the text as written.", False),
]
refusals = [(snip, why, para, ground(clean_text, snip) is None)
            for snip, why, para in FABRICATED]
n_refused = sum(1 for *_, refused in refusals if refused)

# --- filing identity, derived from the filename (stays company-agnostic) ---
parts = filing_path.stem.split("_")
company = parts[0].title() if parts else filing_path.stem
fdate = parts[1] if len(parts) > 1 else ""
fform = parts[2].replace("-", "-") if len(parts) > 2 else "10-K"

# --- hero + stats + filing bar (one render) --------------------------------
stats = [
    (str(len(results)), "Checks run", ""),
    (str(n_grounded), "Grounded findings", "green"),
    (f"{n_refused}/{len(FABRICATED)}", "Fabricated claims refused", "green"),
    (f"{len(clean_text) // 1000}K", "Chars parsed", ""),
]
stat_html = "".join(
    f'<div class="ts-stat"><div class="ts-stat-num {cl}">{esc(num)}</div>'
    f'<div class="ts-stat-lbl">{esc(lbl)}</div></div>'
    for num, lbl, cl in stats
)
pills = [
    f'<span class="ts-pill"><b>{esc(company)}</b></span>',
    f'<span class="ts-pill">{esc(fform)}</span>',
]
if fdate:
    pills.append(f'<span class="ts-pill">filed <b>{esc(fdate)}</b></span>')
pills.append(f'<span class="ts-pill"><b>{n_chunks:,}</b> traceable chunks</span>')

st.markdown(
    '<div class="ts-eyebrow">SEC 10-K diligence · with receipts</div>'
    '<div class="ts-title">Tearsheet</div>'
    '<div class="ts-tagline">Reads a company\'s SEC 10-K and flags what a '
    'diligence analyst would care about — and <b>every claim is citation-linked '
    'to the exact characters in the filing</b>. No verified source, no claim.</div>'
    f'<div class="ts-stats">{stat_html}</div>'
    f'<div class="ts-filingbar">{"".join(pills)}</div>',
    unsafe_allow_html=True,
)

# --- findings --------------------------------------------------------------
cards = "".join(finding_card(name, f, clean_text) for name, f in results)
st.markdown(
    '<div class="ts-sec">Diligence findings</div>' + cards,
    unsafe_allow_html=True,
)

# --- the refusal demo: the hero of the product -----------------------------
refuse_cards = ""
for snip, why, para, refused in refusals:
    tag = '<span class="ts-tag">paraphrase of the real finding</span>' if para else ""
    if refused:
        verdict = (f'<div class="ts-verdict"><span class="x">✕</span>REFUSED — dropped. '
                   f'<span class="why">{esc(why)}</span></div>')
    else:
        # Should be impossible. If it happens, say so loudly, don't hide it.
        verdict = ('<div class="ts-verdict bug"><span class="x">!</span>'
                   'BUG: the guard accepted a fabricated snippet.</div>')
    refuse_cards += (
        f'<div class="ts-refuse{" para" if para else ""}">'
        f'<div class="ts-refuse-claim">“{esc(snip)}”{tag}</div>{verdict}</div>'
    )

st.markdown(
    '<div class="ts-sec">🛡️ The grounding guard — watch it refuse</div>'
    '<div class="ts-tagline" style="margin-bottom:1.2rem">LLMs hallucinate '
    'plausible-sounding financial facts. Tearsheet\'s guard is <b>dumb and '
    'deterministic on purpose</b>: a claim survives only if its exact words '
    'physically exist in the filing. Four fabricated disclosures — including a '
    'paraphrase of the genuine finding — every one refused.</div>'
    + refuse_cards
    + f'<div class="ts-summary"><b>{n_refused} of {len(FABRICATED)} fabricated '
    'claims refused.</b> Refusing is the feature: “I can’t prove it, so I won’t '
    'say it.”</div>',
    unsafe_allow_html=True,
)

# --- footer ----------------------------------------------------------------
st.markdown(
    '<div class="ts-foot">Built with Python · Streamlit · BeautifulSoup over live '
    'SEC EDGAR filings. The proposer is deterministic regex; the grounding guard '
    'is what makes every citation trustworthy. <b>v1 — one company, two checks, '
    'one honest metric.</b> &nbsp;·&nbsp; '
    '<a href="https://github.com/metro-dev26/tearsheet" target="_blank">'
    'Source on GitHub →</a></div>',
    unsafe_allow_html=True,
)
