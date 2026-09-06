from src.core.recurrence import describe, recurrence_from_parameters
from datetime import date

cases = [
    ("le 15 janvier ET juillet", {"repeat": "yearly", "months": [1, 7], "month_days": [15]}),
    ("le 1 ET le 15 mars", {"repeat": "yearly", "months": [3], "month_days": [1, 15]}),
    ("repare depuis monthly", {"repeat": "monthly", "months": [1, 7], "month_days": [15]}),
]
for label, params in cases:
    spec = recurrence_from_parameters(times=["08:00"], today=date(2026, 9, 6), **params)
    print(f"{label:28} bymonth={spec.bymonth} bymonthday={spec.bymonthday}")
    for lang in ("fr", "en", "de"):
        print(f"    {lang}: {describe(spec, lang)}")
