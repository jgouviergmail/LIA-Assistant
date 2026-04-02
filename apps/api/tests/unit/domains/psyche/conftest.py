"""Conftest for psyche unit tests.

Ensures all SQLAlchemy models are registered before tests run,
preventing mapper configuration errors when models reference each other.
"""

from src.infrastructure.database.registry import import_all_models

import_all_models()
