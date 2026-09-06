from src.core.recurrence import RecurrenceSpec, describe

def spec(**kw):
    base = {"anchor_date": "2026-03-01",
            "times": {"mode": "at", "at": [{"hour": 9, "minute": 0}]}}
    return RecurrenceSpec.model_validate({**base, **kw})

cases = {
    "mensuel 1 jour": spec(freq="monthly", bymonthday=[15]),
    "mensuel 2 jours": spec(freq="monthly", bymonthday=[1, 15]),
    "annuel 1 mois 1 jour": spec(freq="yearly", bymonth=[3], bymonthday=[15]),
    "annuel 2 mois 2 jours": spec(freq="yearly", bymonth=[3, 11], bymonthday=[1, 15]),
}
for label, s in cases.items():
    print(label)
    for lang in ("fr", "en", "es", "de", "it", "zh-CN"):
        print(f"   {lang:6} {describe(s, lang)}")
