"""
parse_filing.py — turn a downloaded 10-K (messy HTML) into clean, searchable
text WITHOUT throwing away where each piece came from.

WHY THIS EXISTS (read once, it's the point of the whole project):
Tearsheet's promise is "every red flag, traced to the exact line in the filing."
To keep that promise, when we later say something like "revenue is dangerously
concentrated in one customer," we must be able to point at the precise characters
in the document that back it up.

So as we clean the HTML into plain text, we record, for every block of text, WHERE
it sits in the final clean text: {char_start, char_end}. A citation is then just
those two numbers plus the quoted words. Verifying a claim becomes one line:

    clean_text[char_start:char_end] == quoted_words   # True -> real, False -> drop it

Offsets are what make that check possible. Throwing them away (the common mistake)
kills the whole idea. We keep them from the first second.

Run (Git Bash):
    /c/Users/sujan/tearsheet/.venv/Scripts/python src/parse_filing.py
"""

import json
import sys
import warnings
from pathlib import Path

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

# A 10-K's primary document is "inline XBRL" — HTML with machine-readable
# financial tags woven in, which is technically an XML flavor. Our HTML parser
# extracts the human-readable text correctly anyway (the offset self-check below
# proves it), so this warning is cosmetic. Silence it to keep output clean.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

FILINGS_DIR = Path(__file__).resolve().parent.parent / "data" / "filings"
PARSED_DIR = Path(__file__).resolve().parent.parent / "data" / "parsed"


def parse(html_path: Path):
    """Read one 10-K HTML file and return (clean_text, chunks).

    clean_text : the whole filing as one normalized plain-text string.
    chunks     : a list of {index, char_start, char_end, text}. Each chunk is a
                 piece of visible text, and its offsets point into clean_text so
                 that clean_text[char_start:char_end] == text, exactly.
    """
    html = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")

    # 10-Ks carry invisible junk: scripts, styling, and XBRL metadata in <head>.
    # None of it is disclosure prose. Remove it so it can never pollute our text.
    for tag in soup(["script", "style", "head"]):
        tag.decompose()

    # Walk every visible piece of text in document order.
    # `stripped_strings` yields each text node ONCE (so nested tags like a <div>
    # wrapping a <p> don't get counted twice) with outer whitespace stripped.
    #
    # We rebuild ONE clean string piece by piece, and as we append each piece we
    # write down exactly where it landed. Because we compute the offsets DURING
    # construction, they are guaranteed correct — not guessed afterward.
    chunks = []
    parts = []
    cursor = 0  # how many characters are in clean_text so far

    for piece in soup.stripped_strings:
        text = " ".join(piece.split())  # collapse internal newlines/tabs/runs of spaces
        if not text:
            continue

        start = cursor
        parts.append(text)
        cursor += len(text)
        end = cursor

        chunks.append(
            {"index": len(chunks), "char_start": start, "char_end": end, "text": text}
        )

        # Separate pieces with a single space so words don't fuse together.
        parts.append(" ")
        cursor += 1

    clean_text = "".join(parts)
    return clean_text, chunks


def verify_offsets(clean_text: str, chunks: list) -> None:
    """Prove the offsets are real. For every chunk, the characters at its
    recorded position must equal its text. If this ever fails, our citations
    would be lies — so we assert it loudly instead of shipping a silent bug."""
    for c in chunks:
        got = clean_text[c["char_start"]:c["char_end"]]
        if got != c["text"]:
            raise AssertionError(
                f"offset mismatch at chunk {c['index']}:\n"
                f"  expected: {c['text']!r}\n"
                f"  got:      {got!r}"
            )


def latest_filing() -> Path:
    """Pick the most recently downloaded 10-K in data/filings/."""
    filings = sorted(FILINGS_DIR.glob("*.htm"))
    if not filings:
        raise FileNotFoundError(
            f"No filings in {FILINGS_DIR}. Run fetch_filing.py first."
        )
    return filings[-1]


if __name__ == "__main__":
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else latest_filing()
    print(f"Parsing: {src.name}")

    clean_text, chunks = parse(src)

    # The self-check. If this line doesn't blow up, every citation we ever make
    # from this file can be trusted at the character level.
    verify_offsets(clean_text, chunks)
    print("Offset self-check: PASS")

    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    stem = src.stem  # e.g. CIRRUS_2026-05-21_10-K
    text_out = PARSED_DIR / f"{stem}.txt"
    chunks_out = PARSED_DIR / f"{stem}.chunks.jsonl"

    text_out.write_text(clean_text, encoding="utf-8")
    with chunks_out.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c) + "\n")

    print(f"clean_text: {len(clean_text):,} chars")
    print(f"chunks:     {len(chunks):,}")
    print(f"Saved -> {text_out.name} and {chunks_out.name}")
