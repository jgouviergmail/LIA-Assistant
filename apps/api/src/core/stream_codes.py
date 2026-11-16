"""Stable response codes shared by assistant and non-web transports."""

HITL_DECISION_STALE_ERROR_CODE = "hitl_decision_stale"
#: A channel turn the person stopped (the chat's Stop, Telegram's ``/stop``): it
#: ended because they asked, which is neither an answer nor a failure to report.
RUN_STOPPED_ERROR_CODE = "run_stopped"
