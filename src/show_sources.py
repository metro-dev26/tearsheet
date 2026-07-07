"""
show_sources.py — print the two filing regions the eval checks, so a human can
read them and confirm the tool's numbers are really in the document.

Run (Git Bash):
    /c/Users/sujan/tearsheet/.venv/Scripts/python src/show_sources.py
"""

from pathlib import Path

PARSED = Path(__file__).resolve().parent.parent / "data" / "parsed" / "CIRRUS_2026-05-21_10-K.txt"

text = PARSED.read_text(encoding="utf-8")

print("=" * 70)
print("REGION 1 — customer concentration (should name Apple Inc. + 91 percent)")
print("=" * 70)
print(text[35843:36251])
print()
print("=" * 70)
print("REGION 2 — gross margin trend (should say 52.8% FY2026 increased from 52.5% FY2025)")
print("=" * 70)
print(text[175352:175662])
