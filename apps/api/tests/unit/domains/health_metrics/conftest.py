"""Conftest for Health Metrics unit tests.

Ensures all SQLAlchemy models are registered before tests run so that
cross-domain model relationships resolve cleanly.
"""

from src.infrastructure.database.registry import import_all_models

import_all_models()
