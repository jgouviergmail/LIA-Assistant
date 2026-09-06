from datetime import date
from src.core.recurrence import describe, recurrence_from_parameters
s = recurrence_from_parameters(repeat="daily", weekdays=[1,2,3,4,5], times=["08:00"],
                               today=date(2026, 9, 6))
print("daily+weekdays  fr:", describe(s, "fr"))
print("                en:", describe(s, "en"))
m = recurrence_from_parameters(repeat="monthly", months=[1,7], month_days=[15], times=["08:00"],
                               today=date(2026, 9, 6))
print("monthly+months  fr:", describe(m, "fr"))
print("                en:", describe(m, "en"))
