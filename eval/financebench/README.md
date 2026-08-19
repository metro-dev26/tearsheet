\# FinanceBench (open subset) — local cache



This folder caches the \*\*150-row open-source subset\*\* of FinanceBench, used ONLY to

measure Tearsheet's grounding guard (see `docs/financebench-eval-design.md`).



\- \*\*Source:\*\* https://raw.githubusercontent.com/patronus-ai/financebench/main/data/financebench\_open\_source.jsonl

\- \*\*Paper / dataset:\*\* Islam et al., Patronus AI — https://huggingface.co/datasets/PatronusAI/financebench

\- \*\*License:\*\* CC-BY-NC-4.0 (attribution required, non-commercial).



The `.jsonl` is \*\*gitignored\*\* (not redistributed). Fetch it with:



&#x20;   /c/Users/sujan/tearsheet/.venv/Scripts/python -c "import sys; sys.path.insert(0,'src'); from financebench\_data import download; print(download())"

