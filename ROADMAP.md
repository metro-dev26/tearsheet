# Tearsheet — Improvement Roadmap

Researched July 7 2026 (deep-research pass: commercial tools, grounding best practices,
SEC tooling landscape, analyst red-flag checklists, eval practices).
**RULE: tiers are sequential. Nothing in a tier starts until the tier above is done.**

## Headline findings (interview ammo — use these)

- **Tearsheet's guard is stricter than commercial tools publicly claim.** Hebbia sells
  *sentence-level* citations as its differentiator vs Rogo (Rogo = response-level only).
  Tearsheet does **character-offset, deterministic, verbatim-or-refuse** — and the method
  is open code, while every vendor keeps theirs proprietary. Say this plainly.
- **Fintool was acquired by Microsoft (April 2026)** — market validation for the category.
  Pitch line: "Microsoft just bought a company doing this; here's my working miniature
  with a stricter citation guarantee."
- Char-offset hallucination detection is a real research methodology (RAGTruth benchmark;
  Anthropic's Citations API returns the same char-start/end structure). Not ad hoc.
- Known limitation to state honestly in README: the guard verifies **correctness** (the
  quote exists, verbatim, at the cited offsets) not **faithfulness** (that the claim's
  interpretation matches the quote's meaning) — per "Correctness is not Faithfulness in
  RAG Attributions" (arXiv 2412.18004). Naming this unprompted reads as maturity.

## GATE — v1 ship (do these, in order, before ANY tier below)

1. **git commit.** Five sessions uncommitted. Highest risk in the project.
2. **Gold-set eval** (`eval/`): 20–30 hand-labeled claims from the Cirrus 10-K.
   Report precision/recall + the raw confusion matrix, plus guard rejection rate —
   and manually audit a sample of REJECTED claims to confirm they're true negatives
   (fastest way to catch a silent guard bug). Honest framing: "evaluated against a
   30-claim hand-labeled gold set; not yet validated at scale."
3. **Unicode normalization in parse_filing**: smart quotes (U+2019 etc.), non-breaking
   spaces, dashes, whitespace collapsing — normalize for matching, cite original offsets.
   Already a known issue (session 3); research confirms it's the single highest-value,
   lowest-effort grounding fix.

## Tier 1 — depth on the small scope (cheap, post-ship)

4. Concentration check sets `concern = pct > 10` (historical SEC significant-customer
   threshold; note the bright-line rule was dropped Nov 2020 — still defensible as the
   conventional benchmark). Fixes the neutral-badge gap in the UI.
5. **Going-concern check** — the single most severe red flag, near-verbatim standardized
   auditor phrasing ("substantial doubt", "ability to continue as a going concern"),
   near-zero false-positive regex. Highest signal-to-effort of any new check. Fits the
   propose/verify seam with zero architecture change.
6. Guard **near-miss debug flag**: if exact match fails, rapidfuzz ratio > 95 surfaces
   "near-match, needs review" instead of a silent drop. Debug signal only — does NOT
   weaken the deterministic pass/fail guarantee.
7. README paragraph on the correctness-vs-faithfulness limitation (see headline findings).

## Tier 2 — the resume-changing upgrades

8. **XBRL via `edgartools`** (actively maintained, v5.40+, MIT): pull `us-gaap:Revenues` /
   `us-gaap:GrossProfit` from structured XBRL tags instead of regexing prose for the
   margin check. THE biggest gap vs what Fintool/Rogo actually sell — "reading the
   machine-readable financial statement, not scraping the words." Keep regex+guard for
   qualitative claims (concentration language, going concern) where XBRL doesn't apply.
9. **LLM proposer behind the guard** (Opus 4.8 or Sonnet 5 — NOT Fable, decided sessions
   4/5): swap regex proposer for an LLM reading the filing; nothing below `ground()`
   changes. Safe only AFTER #3 (normalization) and #6 (near-miss flag) exist, or the
   guard will falsely refuse LLM-typed straight quotes.

## Tier 3 — v2 (multi-company, only after Tier 2 ships)

10. Broaden concentration regex for post-2020 principles-based disclosure language
    ("a significant customer" without hard percentages) — required for filers that
    don't disclose like Cirrus does.
11. Restatement flag via **presence of a 10-K/A amendment** in the EDGAR filing index
    (structural check, high precision) — not prose regex.
12. Section-aware parsing: tag chunks by 10-K item (1A Risk Factors, 7 MD&A) so
    citations read "Item 7, chars X–Y".
13. Real DB (companies/filings/chunks/claims, claims FK'd to chunks) + multi-company.

## Parked (real analyst checks that DON'T fit the current architecture — honesty > faking)

- Auditor change/resignation: lives in 8-K Item 4.01, a filing type Tearsheet doesn't
  fetch. Add only if/when the fetcher grows beyond 10-Ks.
- Inventory/receivables divergence (Beneish-style), non-GAAP divergence, covenant
  analysis: numeric XBRL comparisons or credit-agreement exhibits — out of scope until
  Tier 2 #8 exists. Saying "my tool doesn't do this and here's why" is more credible
  than a weak approximation.

## Eval metric names to use (credible framings)

- **Citation precision** (cited quote actually supports the claim)
- **Extraction recall** (of facts a human analyst would flag, fraction surfaced)
- **Guard rejection rate** + audited sample of rejections
- Distinguish citation *correctness* from *faithfulness* when asked.
