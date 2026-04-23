"""Conftest for the Briefing domain unit tests.

Imports all SQLAlchemy models so cross-domain relationships resolve at module load.
"""

from src.infrastructure.database.registry import import_all_models

import_all_models()
