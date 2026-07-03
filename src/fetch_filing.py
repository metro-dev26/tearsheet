"""
fetch_filing.py — pull a company's latest 10-K from SEC EDGAR.

The flow mirrors how you'd find a filing by hand:
  1. Ticker (CRUS) -> CIK, the SEC's internal company id.
  2. CIK -> the company's filing history (a JSON index).
  3. Find the most recent 10-K in that history.
  4. Download that filing's primary document to data/filings/.

SEC rule you must respect: every request needs a User-Agent header that
identifies you (a name + email). No User-Agent => SEC blocks you. This is a
real-world API manners detail, not optional.
"""

import json
import sys
from pathlib import Path

# Make Python trust the OS certificate store. On some networks (incl. this
# machine's) corporate/AV SSL interception breaks the default certificate
# bundle; truststore routes around that. Harmless everywhere else.
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

import requests

# SEC wants a descriptive, contactable User-Agent.
HEADERS = {"User-Agent": "diligence-engine Tam sujanss122@gmail.com"}

# Where downloaded filings land.
FILINGS_DIR = Path(__file__).resolve().parent.parent / "data" / "filings"


def cik_for_ticker(ticker: str) -> int:
    """Look up a company's CIK from its ticker. Never hardcode the CIK —
    look it up, so the tool works for any company later."""
    url = "https://www.sec.gov/files/company_tickers.json"
    data = requests.get(url, headers=HEADERS, timeout=30).json()
    ticker = ticker.upper()
    for row in data.values():
        if row["ticker"] == ticker:
            return int(row["cik_str"])
    raise ValueError(f"Ticker {ticker} not found in SEC ticker map")


def latest_10k(cik: int) -> dict:
    """Return metadata for the company's most recent 10-K."""
    # CIK must be zero-padded to 10 digits for this endpoint.
    url = f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
    sub = requests.get(url, headers=HEADERS, timeout=30).json()

    # filings.recent is column-oriented: parallel arrays, one index per filing.
    recent = sub["filings"]["recent"]
    for i, form in enumerate(recent["form"]):
        if form == "10-K":
            return {
                "company": sub["name"],
                "form": form,
                "filing_date": recent["filingDate"][i],
                "accession": recent["accessionNumber"][i],
                "primary_doc": recent["primaryDocument"][i],
                "cik": cik,
            }
    raise ValueError("No 10-K found in recent filings")


def download(meta: dict) -> Path:
    """Download the filing's primary document (the actual 10-K HTML)."""
    accession_nodash = meta["accession"].replace("-", "")
    url = (
        f"https://www.sec.gov/Archives/edgar/data/"
        f"{meta['cik']}/{accession_nodash}/{meta['primary_doc']}"
    )
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()

    FILINGS_DIR.mkdir(parents=True, exist_ok=True)
    out = FILINGS_DIR / f"{meta['company'].split()[0]}_{meta['filing_date']}_10-K.htm"
    out.write_text(resp.text, encoding="utf-8")
    return out


if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "CRUS"

    cik = cik_for_ticker(ticker)
    print(f"{ticker} -> CIK {cik}")

    meta = latest_10k(cik)
    print(f"Found: {meta['company']} {meta['form']} filed {meta['filing_date']}")

    path = download(meta)
    size_mb = path.stat().st_size / 1_000_000
    print(f"Saved -> {path}  ({size_mb:.1f} MB)")
