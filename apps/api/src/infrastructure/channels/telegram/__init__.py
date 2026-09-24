"""Telegram channel infrastructure.

python-telegram-bot 22.2 deprecated its numeric time periods: a future major
version returns them as ``datetime.timedelta``, and until then every numeric
read warns. The library's documented opt-in is the ``PTB_TIMEDELTA``
environment variable, which it reads at each access — so the package opts in
here, once, for every module that reads such a value. ``setdefault`` leaves an
operator's explicit choice in charge, which is why ``flood_control`` still
accepts a number.
"""

import os

os.environ.setdefault("PTB_TIMEDELTA", "true")
