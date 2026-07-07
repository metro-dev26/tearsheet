# Tearsheet — Project Context

## What this project is (plain English)
A tool that reads a public company's SEC annual report (the 10-K) and automatically
flags the warning signs an investor or buyer would care about — and for every flag,
shows the **exact line in the document** it came from (the proof). Think "a robot
junior diligence analyst, with receipts." It is a scoped, working slice of what the
company Rogo does. The name "Tearsheet" = finance term for a one-page company
snapshot; the tool reads the giant report and produces the one page that matters.

## Who you're working with — READ FIRST
- The user is **Tam** (he calls Claude "John"). Final-year CSE-AIML student in Chennai.
  Long-term goal: a finance/investor seat abroad. This project is his **flagship resume
  artifact** for the positioning "I build the products finance runs on."
- He is a **relative beginner** (basic Python). **TEACH every step in plain English** —
  explain *what* + *why* + the *finance reasoning* before building anything. Each session
  must end with him able to EXPLAIN what was built. A step he can't explain didn't happen.
- Tone: direct, declarative, grounded, no hedging. But when he's confused, **slow down and
  re-explain plainly, never condescending.** He will say so when he's lost — honor that.
- Time budget: **~1 hour/day** on this. The rest of his day is SQL, Python, DSA. Do not let
  this project grow past that cap.

## THE CARDINAL RULE — scope discipline
- Tam's failure mode is **over-building and replanning instead of shipping.** It killed a
  prior project ("portfolio-risk-ml" — never finished). His shipped one (a portfolio risk
  dashboard) succeeded because it stayed simple and got finished.
- **Build the simple working spine FIRST, then add depth.** Advanced is *earned after* the
  simple version runs — never started with.
- "Advanced" = **depth on the small scope** (eval rigor, grounding, edge-case handling),
  NOT more features/companies/UI. In session 1 he pushed 3 times to make it bigger/"really
  advanced/flagship." Hold the line warmly each time.

## Scope of v1 (the ONLY version being built)
- **ONE company: Cirrus Logic** (ticker `CRUS`, CIK `772406`). Chosen because it has ONE
  clean, obvious, verifiable flag: extreme **customer concentration** — the vast majority of
  revenue comes from a single customer (Apple), disclosed plainly in the 10-K. Easy to
  confirm the engine got the right answer (we already know the truth).
- **TWO checks:** (1) customer concentration [lead — easiest win]; (2) a profit/margin
  **trend** across multiple years.
- **The differentiator — the grounding guard:** every claim must quote the exact source
  snippet; string-match it against the filing; if it doesn't verify, **drop the claim.** The
  tool *refusing* to make an ungrounded claim is the hero of the demo.
- **One honest metric:** extraction accuracy vs hand-keyed numbers across a small gold set
  (~5 filings, not 20).
- Front end: **Streamlit.** NO auth, NO Supabase, NO multi-company data room, NO agentic loop
  in v1. The engine is the moat; the SaaS wrapper is later/optional.
- Later expansion (ONLY after v1 ships): covenant/leverage check (candidate company:
  Carnival), more companies, web frontend.

## Tech + how to run
- Python 3.13, project virtualenv at `.venv`. Deps in `requirements.txt`:
  requests, beautifulsoup4, lxml, pandas, truststore.
- Run with the venv's Python, e.g. (Git Bash):
  `/c/Users/sujan/tearsheet/.venv/Scripts/python src/fetch_filing.py CRUS`
- **Gotchas:** SEC EDGAR blocks requests without an identifying `User-Agent` header.
  Tam's network does SSL interception, so the code calls `truststore.inject_into_ssl()`
  to use the OS trust store (same issue that broke yfinance in his other project).

## Progress
### Session 1 — Jun 24–25 2026 (DONE)
- Scaffolded: `src/`, `data/filings/` (gitignored download cache), `eval/` (future gold set),
  git repo, venv, README.
- Built `src/fetch_filing.py`: ticker → CIK (via SEC company_tickers.json) → submissions API
  → finds latest 10-K → downloads primary doc to `data/filings/`.
- Ran it: pulled Cirrus Logic 10-K filed 2026-05-21 (1.7 MB) →
  `data/filings/CIRRUS_2026-05-21_10-K.htm`.
- Named the project "Tearsheet."

### Session 2 — Jul 2 2026 (DONE)
- Built `src/parse_filing.py`: raw 10-K HTML → `clean_text` (one normalized string) +
  `chunks` (list of {index, char_start, char_end, text}), offsets computed DURING
  construction so `clean_text[start:end] == text` exactly. `verify_offsets()` asserts the
  invariant on every run — this is what makes citations trustworthy.
- Handled inline-XBRL parser warning (cosmetic; suppressed, extraction verified sound).
- Ran on Cirrus 10-K: 304,621 chars, 5,381 chunks, self-check PASS. Outputs saved to
  `data/parsed/CIRRUS_2026-05-21_10-K.txt` and `.chunks.jsonl` (data/parsed gitignored? — NO,
  add to .gitignore next session; it's derived data).
- Sanity-confirmed the customer-concentration disclosure ("our largest customer," Apple/FaceID)
  survived cleaning and is present in clean_text — ready to ground next session.
- NOTE: repo still has ZERO commits. Session 1 + 2 work is all uncommitted. Commit when Tam says go.

### Session 3 — Jul 5 2026 (DONE)
- Found the real quantitative flag in Cirrus 10-K: "we had one end customer, Apple Inc., ...
  represented approximately 91 percent ... of ... total net sales" (chars 35,943-36,151).
- Built the PROPOSE/VERIFY seam — the core architecture:
  - `src/ground.py` — the GROUNDING GUARD (the moat). `ground(clean_text, snippet)` -> {snippet,
    char_start, char_end} if verbatim-present, else None (refuse). Dumb, deterministic, trusts
    nobody. Should ~never change even when checks get smarter.
  - `src/checks.py` — `check_customer_concentration(clean_text)`: regex proposes claim + exact
    snippet, hands snippet to guard; no verification -> no finding. Regex is a placeholder for a
    future LLM proposer — nothing below the `ground()` call changes when we swap it.
  - `src/run_diligence.py` — wires parse -> check -> ground; prints grounded finding w/ context
    AND a REFUSAL demo (fake "Samsung 45%" snippet -> guard returns None -> dropped).
- Ran: real flag grounded correctly; fabricated claim refused. Both halves work.
- KNOWN ISSUE (deferred, real): filing uses curly apostrophe (U+2019); LLM proposers will type
  straight ' and the guard will wrongly refuse over punctuation. Fix = normalize smart quotes
  (and similar: curly quotes, non-breaking spaces, dashes) during parse. NEXT-ish brick.
- Uncommitted (git). Terminal shows Company��s = cp1252 console print artifact, NOT data corruption
  (guard's assert passed).

### Session 4 — Jul 5 2026 (DONE) — v1 ENGINE COMPLETE
- Discussed Fable 5: decided NOT to use it for Tearsheet. It's the priciest model ($10/$50 per M,
  2x Opus); Tearsheet's LLM job is document extraction, which Opus tops out on. KEY INSIGHT the
  grounding guard means the proposer can be a CHEAPER model safely — the guard catches
  hallucinations deterministically. When we wire an LLM proposer (later brick): Opus 4.8 (or
  Sonnet 5 for cost) + structured outputs, NOT Fable.
- Built `check_margin_trend` in checks.py (2nd v1 check): regex finds the YoY gross-margin sentence
  ("gross margin of 52.8 percent for FY2026 increased from FY2025 gross margin of 52.5 percent"),
  extracts cur/prev/direction, grounds the snippet. Reports trend BOTH ways; sets concern=True only
  if margin declined > _MARGIN_DECLINE_CONCERN_PTS (1.0 pt). Cirrus: 52.5->52.8, +0.3pt, [ok].
- Refactored run_diligence.py to loop over a `checks` list (adding a check = one list entry) and
  surface [CONCERN]/[ok] flags.
- MILESTONE: v1 scope (1 company / 2 checks / citation guard) is functionally COMPLETE. Engine =
  the moat = done. Both checks grounded; refusal demo still passes.

### Build-first mode (Tam's call, Session 4)
Tam chose build-first, batch-learning-at-the-end. Per-brick teach-backs paused. Code stays heavily
commented as the learning material. OWED: one consolidation session where Tam explains the whole
engine back (propose/verify seam, grounding guard, both checks) before it counts as learned.

### Session 5 — Jul 7 2026 (DONE — Streamlit prep + engine refactor)
- Reconciled: engine (ground.py, checks.py, run_diligence.py) confirmed working — both checks ground,
  refusal demo passes. STILL UNCOMMITTED (untracked) as of session end + CLAUDE.md modified. Standing risk.
- Installed Streamlit (1.59.0) into .venv — it wasn't present.
- Refactored `run_diligence.py`: extracted `run_all_checks(clean_text)` backed by a single `CHECKS`
  registry (list of (name, fn)). CLI now loops over it; the coming Streamlit app will drive off the
  SAME registry so the two can't drift. Verified CLI output unchanged after the refactor.
- Fable 5 question (again): decided NO, confirmed with live pricing — Fable $10/$50 per 1M vs Opus 4.8
  $5/$25 (2x). Reasoning: (a) no LLM in Tearsheet yet, the proposer is still regex — today's brick is the
  UI, not the model; (b) the grounding guard is precisely what lets the proposer be a CHEAP model safely,
  so paying 2x for the priciest model to do extraction Opus tops out on, behind a guard that catches its
  mistakes anyway, defeats the design. When the LLM brick comes: Opus 4.8 (or Sonnet 5 at $3/$15), NOT Fable.
- `app.py` NOT built yet — installed + refactored + designed, ready to write next session. Session ended
  before the file was written.

### NEXT BRICKS (v1 remaining — engine done, these are the wrapper + proof)
1. **Honest metric**: extraction accuracy vs a small hand-keyed gold set (~5 filings) in eval/.
   Proves the numbers we extract match reality. This is the credibility layer.
2. **Streamlit front end**: show findings + citations + the refusal behavior. The demo surface.
3. (Deferred/optional) harden grounding: normalize smart quotes (U+2019) / whitespace in
   parse_filing so a future LLM proposer's straight-quote snippets don't get falsely refused.
Pick ONE per session. Engine is the moat; wrapper is next.

## Don't forget (Tam's other commitment)
He owes a LinkedIn post for his shipped Portfolio Risk Dashboard + pinning that repo — meant
to happen this week. Nudge him.
