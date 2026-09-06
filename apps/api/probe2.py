from src.core.recurrence import RecurrenceSpec, describe, recurrence_from_parameters
from datetime import date

s = RecurrenceSpec(freq="daily", anchor_date="2026-09-07",
                   times={"mode": "at", "at": [{"hour": 8, "minute": 0}]},
                   byweekday=(1, 2))
print("A) phrase montree a l utilisateur :", describe(s, "fr"))

s2 = RecurrenceSpec(freq="monthly", anchor_date="2026-09-15",
                    times={"mode": "at", "at": [{"hour": 8, "minute": 0}]},
                    bymonthday=(15,), bymonth=(1, 7))
print("B) phrase montree a l utilisateur :", describe(s2, "fr"))

print()
print("=== le chemin conversationnel peut-il produire cette forme ? ===")
for params in (
    {"repeat": "daily", "weekdays": [1, 2, 3, 4, 5], "times": ["08:00"]},
    {"repeat": "monthly", "month_days": [15], "months": [1, 7], "times": ["08:00"]},
    {"repeat": "weekly", "weekdays": [1], "month_days": [15], "times": ["08:00"]},
):
    try:
        spec = recurrence_from_parameters(today=date(2026, 9, 6), **params)
        print(" ", params)
        print("    -> ACCEPTE :", describe(spec, "fr"), "| byweekday=", spec.byweekday,
              "bymonth=", spec.bymonth, "bymonthday=", spec.bymonthday)
    except Exception as exc:
        print(" ", params)
        print("    -> refuse :", type(exc).__name__, str(exc)[:90])
