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


def ground(clean_text: str, snippet: str):
    """Verify `snippet` appears verbatim in `clean_text`.

    Returns {snippet, char_start, char_end} if it does — a citation you can
    trust, because clean_text[char_start:char_end] == snippet exactly.

    Returns None if it doesn't — the claim is ungrounded and must be dropped.
    Refusing is a feature, not a failure.
    """
    idx = clean_text.find(snippet)
    if idx == -1:
        return None

    start = idx
    end = idx + len(snippet)

    # Paranoia: prove the offsets we're about to hand out are exact. If this
    # ever fails, something is deeply wrong and we do NOT want to emit a citation.
    assert clean_text[start:end] == snippet

    return {"snippet": snippet, "char_start": start, "char_end": end}
