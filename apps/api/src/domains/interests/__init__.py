"""
Interests Domain.

Handles user interest learning and proactive notifications:
- Interest extraction from conversations
- Bayesian weight evolution
- Proactive content generation and delivery
- User feedback handling

Components:
- models.py: SQLAlchemy models (UserInterest, InterestNotification)
- schemas.py: Pydantic schemas for API
- repository.py: Database access layer
- router.py: API endpoints
- proactive_task.py: InterestProactiveTask implementation
- services/: Business logic services
"""

from src.domains.interests.models import InterestNotification, UserInterest

__all__ = [
    "UserInterest",
    "InterestNotification",
]
