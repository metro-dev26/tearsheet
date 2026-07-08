# Tearsheet

*Automated first-pass diligence on a company's SEC filings — every red flag traced to the exact line it came from.*

**[▶ Live demo](https://YOUR-APP.streamlit.app)**  ·  built with Python + Streamlit over live SEC EDGAR filings

![Tearsheet screenshot](docs/screenshot.png)

---

## The problem

Reading a 10-K for diligence is slow, and tools that summarize filings with an
LLM have a fatal flaw for finance work: they hallucinate. A number that looks
right but isn't traceable to the document is worse than no number at all.

Tearsheet takes the opposite stance. It will only surface a finding it can
**quote verbatim from the filing and prove with an exact character span.** If it
can't prove a claim, it drops it. A tool that refuses to guess is the point.

## What it does

Given a company's latest 10-K, Tearsheet:

1. Fetches and parses the filing from SEC EDGAR into clean text, preserving exact
   character offsets so any span can be traced back to the source.
2. Runs a set of transaction-advisory checks that a junior diligence analyst
   would run.
3. Grounds every finding: the claimed evidence must string-match the filing
   exactly, or the finding is discarded.
4. Presents each finding with its claim, the verbatim quote, and the exact
   character range it came from.

## How it works — the propose/verify seam

The architecture separates *proposing* a claim from *verifying* it:

```
parse_filing.py   raw 10-K HTML  ->  clean_text (+ verified char offsets)
checks.py         propose:  a check finds a candidate claim + the snippet it rests on
ground.py         verify:   the snippet must appear verbatim in clean_text, or -> refused
```

`ground.py` is the moat. It is deliberately dumb and deterministic — it trusts
nobody, does an exact string match, and returns the character span or nothing.
Because the guard catches ungrounded claims after the fact, the *proposer* is
free to be swapped for a cheaper or smarter model later without weakening the
reliability guarantee.

## The two v1 checks (on Cirrus Logic, CRUS)

| Check | Finding on Cirrus 10-K | Proof |
|---|---|---|
| **Customer concentration** | One end customer (Apple Inc.) ≈ **91%** of net sales | chars 35,943–36,151 |
| **Margin trend** | Gross margin **52.5% → 52.8%** YoY (improved, no concern) | chars 175,452–175,562 |

Cirrus was chosen because it has one clean, publicly known flag — extreme
single-customer concentration — so the engine's answer can be checked against
reality.

## Honest evaluation

The engine is graded against a **human-keyed gold set** — the true answers read
out of the filing by a person, not by the tool. The eval is designed to refuse
to be trusted until a human has attested to the gold values (it exits nonzero
and prints `PROVISIONAL` otherwise), so the metric can't quietly become
circular.

```
Extraction accuracy (engine vs human truth):   8/8   = 100%
Citation validity   (offsets point at quote):  2/2
Guard rejection     (fabricated claims dropped): 4/4
RESULT: ALL PASS  (human-verified)
```

The guard-rejection set includes a *paraphrase of the real disclosure* — same
meaning, different words — because paraphrase is exactly how an LLM proposer
would fail. The guard refuses it anyway.

## Run it locally

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt

# Fetch a filing (SEC requires an identifying User-Agent; set in fetch_filing.py)
python src/fetch_filing.py CRUS

# Run the checks in the terminal
python src/run_diligence.py

# Or launch the UI
streamlit run src/app.py

# Grade the engine against the gold set
python src/run_eval.py
```

## Tech

Python 3.13 · Streamlit · BeautifulSoup/lxml for parsing · SEC EDGAR as the
data source. No LLM in the loop yet — the proposer is deterministic regex, which
keeps the engine auditable while the grounding seam proves out. An LLM proposer
behind the same guard is the next step.

## Scope & limitations

This is a scoped, working slice — not a product. v1 covers **one company, two
checks, one honest metric.** The proposer is regex, not an LLM, so it only
recognizes disclosure phrasings it was written for; generalizing to arbitrary
filers is deliberately deferred. The roadmap (see `ROADMAP.md`) covers a
going-concern check, unicode/whitespace normalization to harden grounding, XBRL
via `edgartools`, and swapping in an LLM proposer behind the existing guard.
