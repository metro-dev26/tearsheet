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

### NEXT BRICK (start here next session)
1. **Locate the customer-concentration disclosure sentence** (the flag) in the clean_text and
   ground it: return {claim, snippet, char_start, char_end} and verify the snippet matches.
   That's the first real diligence output — the grounding guard in action.
2. Add `data/parsed/` to `.gitignore` (derived data, shouldn't be committed).

## Don't forget (Tam's other commitment)
He owes a LinkedIn post for his shipped Portfolio Risk Dashboard + pinning that repo — meant
to happen this week. Nudge him.
