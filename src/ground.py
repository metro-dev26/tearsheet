"""
ground.py — THE GROUNDING GUARD. This is the moat.

One job, done deterministically and without trusting anyone: given a claimed
snippet, prove those exact words physically exist in the filing, and report
WHERE. If they don't exist, refuse — return None so the claim gets dropped.

Why this is separate from everything else:
Something else (a regex today, an LLM tomorrow) PROPOSES a claim. That proposer
might paraphrase, round a number, or hallucinate a sentence that reads plausibly
but was never in the document. The guard never trusts it. It only asks one
question — "are these exact characters really in the filing?" — and answers with
proof (offsets) or a refusal. Because it's dumb and deterministic, it can't be
fooled the way a language model can. That's the whole point.

This file should almost never change, even as the checks above it get smarter.
"""

from parse_filing import normalize  # same punctuation-folding the parser uses


def ground(clean_text: str, snippet: str):
    """Verify `snippet` appears verbatim in `clean_text`.

    Returns {snippet, char_start, char_end, occurrences} if it does — a citation
    you can trust, because clean_text[char_start:char_end] == snippet exactly.
    `occurrences` is how many times the snippet appears; >1 means the citation is
    ambiguous (we cite the first) and a caller may choose to flag it.

    Returns None if it doesn't — the claim is ungrounded and must be dropped.
    Refusing is a feature, not a failure.

    We fold the proposer's snippet to the same plain-ASCII form the parser applied
    to clean_text, so a curly-vs-straight quote can't cause a false refusal. This
    is NOT loosening the guard — it's still an exact character match; both sides are
    just compared in one canonical form. (clean_text is assumed already normalized,
    which it is: it comes straight out of parse().)
    """
    # Fold punctuation AND collapse whitespace to the exact same canonical form the
    # parser applied to clean_text (`" ".join(normalize(piece).split())`). The parser
    # squeezes every run of whitespace to a single space — including across table
    # cells and line breaks — so a model that quotes a margin out of a multi-cell
    # table (newlines, double spaces) would be falsely refused unless we squeeze its
    # snippet the same way. This is NOT loosening the guard: it's still an exact match
    # on the visible characters, just whitespace-insensitive, both sides canonicalized.
    snippet = " ".join(normalize(snippet).split())
    if not snippet:
        # An all-whitespace/empty snippet would "match" at position 0 trivially.
        # There is nothing to ground — refuse.
        return None

    idx = clean_text.find(snippet)
    if idx == -1:
        return None

    start = idx
    end = idx + len(snippet)

    # Paranoia: prove the offsets we're about to hand out are exact. Use a real
    # raise, NOT assert — assert is compiled out under `python -O`, and the moat's
    # final integrity check must never be optional.
    if clean_text[start:end] != snippet:
        raise AssertionError(
            f"ground(): offset invariant broken — clean_text[{start}:{end}] != snippet"
        )

    # How many times the snippet appears. find() returns the FIRST, which for a
    # short/duplicated quote may not be the instance the proposer read. We can't
    # know which was meant, so we don't pretend: we cite the first AND report the
    # count, so a caller can flag an ambiguous citation instead of trusting it blind.
    occurrences = clean_text.count(snippet)

    return {
        "snippet": snippet,
        "char_start": start,
        "char_end": end,
        "occurrences": occurrences,
    }
