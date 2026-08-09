"""
llm_propose.py — the LLM PROPOSER. Swap the Cirrus-tuned regex for a model that
actually READS the filing.

THE IDEA (this is the whole point of the brick):
The old proposer (checks.py) is a regex hand-tuned to Cirrus's exact wording. Point
it at a different company that says the same thing in different words and it finds
nothing — that's why Skyworks scored 0/7. An LLM reads for MEANING, so it can find
"Apple ... accounted for 67%" and "we had one end customer, Apple ... represented
approximately 91 percent" as the same KIND of fact, despite the different words.

But an LLM is a brilliant intern who sometimes invents numbers. So we do NOT trust
it. It PROPOSES a claim and a quote; the grounding guard (ground.py) still checks
that the quote physically exists in the filing, character for character, and drops
anything it can't verify. Nothing below the ground() call changes when we swap the
regex for the model — the guard already does the trusting-nobody part.

WHY WE FEED IT clean_text (the parsed text), NOT the raw HTML:
The guard searches clean_text for the model's quote. If the model quotes from the
SAME string the guard will search, "copy it verbatim" is actually achievable. Feed
it raw HTML and it would quote HTML-mangled text the guard could never find.

WHY REST + requests (not Google's SDK):
Tam's network does SSL interception. Google's SDK talks gRPC, which fights that.
requests + truststore already works on this network (fetch_filing.py proves it),
and adds no new dependency.

Run (Git Bash), on the most recent filing:
    /c/Users/sujan/tearsheet/.venv/Scripts/python src/llm_propose.py
Or a specific one:
    /c/Users/sujan/tearsheet/.venv/Scripts/python src/llm_propose.py data/filings/SKYWORKS_2025-11-07_10-K.htm
"""

import json
import sys
import time
from pathlib import Path

import requests
import truststore

from parse_filing import parse, latest_filing
from ground import ground

# Tam's network intercepts SSL; use the OS trust store so requests trusts the
# corporate root cert instead of failing the handshake (same fix as fetch_filing).
truststore.inject_into_ssl()

# gemini-flash-latest: an ALIAS that always resolves to Google's current stable
# "flash" model (the small/fast/cheap tier), free tier, with a ~1M-token context
# window — a whole 10-K (~80k tokens) fits in a single call, so no chunking.
# Why the alias instead of a pinned version (e.g. gemini-3.6-flash): Google retires
# older names (gemini-2.5-flash already 404s for new keys), and the alias survives
# that. TRADEOFF: a pinned model makes an eval perfectly reproducible; "latest" can
# drift. Fine while we're still establishing the baseline — pin it if the eval ever
# becomes a fixed benchmark.
_MODEL = "gemini-flash-latest"
_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{_MODEL}:generateContent"

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

# The free "flash" tier throws transient 429/503s under load ("high demand,
# try again later") that have nothing to do with our request. Retry those a few
# times with growing backoff so one spike doesn't abort an eval mid-run. A 4xx
# that ISN'T rate-limiting (bad key, bad request) is a real error — fail on it
# immediately, don't waste retries.
_RETRY_STATUSES = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 4

# How many percentage points of margin decline we treat as a concern. Mirror the
# regex check so the LLM path and the old path grade a declining margin the same.
_MARGIN_DECLINE_CONCERN_PTS = 1.0


def _load_api_key() -> str:
    """Read GEMINI_API_KEY from the gitignored .env file. Kept tiny on purpose —
    not worth a dependency to parse KEY=VALUE lines. The key NEVER goes in code,
    chat, or git; only in .env (which .gitignore excludes)."""
    if not _ENV_PATH.exists():
        raise FileNotFoundError(
            f"No .env at {_ENV_PATH}. Add a line: GEMINI_API_KEY=your_key_here"
        )
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("GEMINI_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise KeyError("GEMINI_API_KEY not found in .env")


# The instructions we hand the model. The single most important line is the one
# demanding a VERBATIM snippet — it aligns the model with the guard, which will
# reject anything not found in the filing character-for-character.
_PROMPT = """You are a diligence analyst reading a company's SEC 10-K annual report.
The full cleaned text of the filing is given below between the markers.

Find these two facts, using ONLY the text provided:

1. CUSTOMER CONCENTRATION — the single largest customer and what percent of the
   company's total net sales / net revenue it represented in the MOST RECENT
   fiscal year. (Many filers disclose several years at once, e.g. "67%, 69% and
   66%"; take the FIRST / most-recent one.)

2. GROSS MARGIN TREND — the company's gross margin (gross profit as a percent of
   revenue). First pick the MOST PRECISE disclosure of it in the filing: prefer a
   figure stated to a decimal (e.g. "52.8 percent" or "41.2 %") over one rounded to
   a whole number (e.g. "53 %"), because rounding hides real movement. It may be a
   sentence OR a table of figures — whichever states the margin most precisely.
   From that same source, give two numbers:
     - cur_pct  = the MOST RECENT fiscal year's gross margin.
     - prev_pct = the EARLIEST fiscal year's gross margin shown in that SAME source.
                  Filings often show two or three years together (e.g. a table with
                  2025, 2024, 2023, or a sentence comparing this year to last year).
                  Take the oldest year shown in your chosen source, so the trend
                  covers the whole window it discloses and a multi-year decline is
                  NOT hidden by a flat most-recent year.

For EACH fact, you MUST return a "snippet": a run of text COPIED EXACTLY,
CHARACTER FOR CHARACTER, from the filing text below — same words, same numbers,
same punctuation, same spacing. Do NOT paraphrase, summarize, reword, or fix
anything. A separate verifier will search the filing for your snippet and DISCARD
your finding if it is not found exactly. Copy the shortest run of text that still
contains the key numbers.

If a fact is genuinely not disclosed in the text, set its "present" to false and
leave the other fields empty.

FILING TEXT:
<<<
{filing}
>>>
"""

# Structured-output schema: forces Gemini to answer as clean JSON with exactly
# these fields, instead of prose we'd have to re-parse.
_SCHEMA = {
    "type": "object",
    "properties": {
        "customer_concentration": {
            "type": "object",
            "properties": {
                "present": {"type": "boolean"},
                "customer": {"type": "string"},
                "pct": {"type": "number"},
                "snippet": {"type": "string"},
            },
            "required": ["present"],
        },
        "margin_trend": {
            "type": "object",
            "properties": {
                "present": {"type": "boolean"},
                "cur_pct": {"type": "number"},
                "prev_pct": {"type": "number"},
                "snippet": {"type": "string"},
            },
            "required": ["present"],
        },
    },
    "required": ["customer_concentration", "margin_trend"],
}


def _call_gemini(clean_text: str) -> dict:
    """Send the filing to Gemini and get back the raw (UNVERIFIED) proposals as a
    dict. This is the intern's reading — plausible, not yet trusted."""
    body = {
        "contents": [{"parts": [{"text": _PROMPT.format(filing=clean_text)}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": _SCHEMA,
            "temperature": 0,  # extraction, not creativity — be deterministic
        },
    }
    headers = {"x-goog-api-key": _load_api_key()}  # key in header, never the URL
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        resp = requests.post(_ENDPOINT, headers=headers, json=body, timeout=120)
        if resp.status_code == 200:
            break
        # Transient overload/rate-limit: wait and retry (2s, 4s, 8s). Anything
        # else (or the last attempt) is a hard failure we surface immediately.
        if resp.status_code in _RETRY_STATUSES and attempt < _MAX_ATTEMPTS:
            wait = 2 ** attempt
            print(f"  Gemini {resp.status_code} (transient) — retrying in {wait}s "
                  f"[attempt {attempt}/{_MAX_ATTEMPTS - 1}]", file=sys.stderr)
            time.sleep(wait)
            continue
        raise RuntimeError(f"Gemini API {resp.status_code}: {resp.text[:500]}")

    # The model's answer is a JSON string inside the response envelope.
    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


def propose(clean_text: str) -> dict:
    """Read the filing with the LLM, then GROUND every quote it gives back.

    Returns {"customer_concentration": finding|None, "margin_trend": finding|None},
    where each finding has the SAME shape the regex checks produce — so the eval,
    CLI, and UI can consume it identically. A None means either the model said the
    fact isn't present, or its quote failed the guard (dropped, not trusted)."""
    raw = _call_gemini(clean_text)
    return {
        "customer_concentration": _ground_concentration(clean_text, raw.get("customer_concentration", {})),
        "margin_trend": _ground_margin(clean_text, raw.get("margin_trend", {})),
    }


def _ground_concentration(clean_text: str, prop: dict):
    """Turn the model's concentration proposal into a grounded finding, or None."""
    if not prop.get("present") or not prop.get("snippet"):
        return None

    customer = str(prop.get("customer", "")).strip()
    pct = prop.get("pct")

    # The guard has the final say: quote must exist in the filing, verbatim.
    cite = ground(clean_text, prop["snippet"])
    if cite is None:
        return None

    claim = (
        f"Customer concentration risk: a single customer ({customer}) accounted "
        f"for approximately {pct}% of total net sales."
    )
    return {
        "check": "customer_concentration",
        "claim": claim,
        "customer": customer,
        "pct": pct,
        **cite,  # snippet, char_start, char_end
    }


def _ground_margin(clean_text: str, prop: dict):
    """Turn the model's margin proposal into a grounded finding, or None.

    The model gives us only the two raw numbers (most-recent-year margin and the
    earliest-disclosed-year margin) and the quote. WE compute the direction, the
    delta, and the concern flag in code — never let the model do arithmetic we can
    do deterministically. Comparing newest vs oldest disclosed year is deliberate:
    it catches a multi-year slide (e.g. Skyworks 44.2% -> 41.2%) that a
    newest-vs-last-year check would report as 'flat' and hide."""
    if not prop.get("present") or not prop.get("snippet"):
        return None

    try:
        cur = float(prop["cur_pct"])
        prev = float(prop["prev_pct"])
    except (KeyError, TypeError, ValueError):
        return None

    cite = ground(clean_text, prop["snippet"])
    if cite is None:
        return None

    delta = round(cur - prev, 2)  # positive = margin improved
    if delta > 0:
        direction = "increased"
    elif delta < 0:
        direction = "decreased"
    else:
        direction = "remained flat"
    concern = delta <= -_MARGIN_DECLINE_CONCERN_PTS

    claim = (
        f"Gross margin trend: {prev}% -> {cur}%, a {delta:+.1f} pt move ({direction})."
    )
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


def _show_context(clean_text: str, finding: dict, pad: int = 40) -> str:
    s, e = finding["char_start"], finding["char_end"]
    left = clean_text[max(0, s - pad):s]
    right = clean_text[e:e + pad]
    return f"...{left}[[{clean_text[s:e]}]]{right}..."


if __name__ == "__main__":
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else latest_filing()
    print(f"Filing: {src.name}")
    print(f"Model:  {_MODEL}\n")

    clean_text, _chunks = parse(src)
    findings = propose(clean_text)

    for name, finding in findings.items():
        print(f"=== CHECK: {name} ===")
        if finding is None:
            print("No grounded finding (model saw nothing, or its quote failed the guard).")
        else:
            flag = ""
            if finding.get("concern") is True:
                flag = "  [CONCERN]"
            elif "concern" in finding:
                flag = "  [ok]"
            print(f"CLAIM:  {finding['claim']}{flag}")
            print(f"PROOF:  chars {finding['char_start']:,}-{finding['char_end']:,}")
            print(f"QUOTE:  \"{finding['snippet']}\"")
            print(f"IN CONTEXT: {_show_context(clean_text, finding)}")
        print()
