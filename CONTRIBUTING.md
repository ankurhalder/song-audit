# Contributing

Thanks for helping. A few ground rules keep the audit honest.

## Setup

    python -m venv .venv
    . .venv/bin/activate        # Windows: .venv\Scripts\activate
    pip install -e ".[dev]"
    pytest

## Adding a metric

1. Put the measurement in the module that owns the domain (mastering, spectral, music, lyrics).
2. Return plain Python types (floats, ints, lists, dicts) so the JSON stays stable.
3. Wire it into pipeline.py and, if it deserves a score, into score.py with a rule and a fix.
4. Add a test with a synthetic signal where the expected value is provable.

## Rules

- Do not invent metrics. Every number must be traceable to a published method or an explicit, documented heuristic.
- Heuristics are labelled as such in the report. No "AI detection" claims.
- Never commit audio you do not own. tests/ generates its fixtures procedurally.
- Keep the report readable: one recommendation should map to one concrete action.
