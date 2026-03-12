"""
RelevanceEngine - Intelligent Results Ranking and Filtering.

Architecture v3 - Intelligence, Autonomie, Pertinence.

This engine provides:
1. Filter non-relevant results
2. Order by relevance score
3. Intelligent limiting (not always 10)
4. Explain why these results

KEY PRINCIPLE:
Not just sorting by date or name.
Understanding WHAT the user is REALLY looking for
and prioritizing accordingly.

EPISODIC MEMORY:
Uses UserContext for personalized scoring:
- Geographic proximity to home/work
- Interaction history (frequent contacts)
- Learned preferences (favorite place types)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from src.core.config.agents import V3RelevanceConfig, get_v3_relevance_config
from src.core.constants import DEFAULT_LANGUAGE, DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.i18n_v3 import V3Messages
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.domains.agents.analysis.query_intelligence import QueryIntelligence

logger = get_logger(__name__)


@dataclass
class UserContext:
    """User's personal context for episodic memory."""

    user_id: str
    home_location: str | None = None  # "Joinville-le-Pont"
    work_location: str | None = None
    interaction_history: dict[str, int] = field(default_factory=dict)  # item_id -> count
    preferred_place_types: list[str] = field(default_factory=list)  # ["restaurant", "cafe"]
    recent_searches: list[str] = field(default_factory=list)  # Last searches
    timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE
    language: str = DEFAULT_LANGUAGE

    @classmethod
    def default(cls, user_id: str) -> UserContext:
        """Create default context for a user."""
        return cls(
            user_id=user_id,
            home_location=None,
            interaction_history={},
            preferred_place_types=[],
            recent_searches=[],
        )


@dataclass
class RankedResult:
    """Result with relevance score."""

    data: Any
    relevance_score: float  # 0.0 - 1.0
    relevance_reasons: list[str] = field(default_factory=list)
    is_primary: bool = False  # Primary result vs secondary


@dataclass
class FilteredResults:
    """Filtered and ordered results by relevance."""

    primary_results: list[RankedResult]
    secondary_results: list[RankedResult]
    total_found: int
    total_shown: int
    filter_explanation: str  # Why these results

    def all_results(self) -> list[RankedResult]:
        """Get all results in order."""
        return self.primary_results + self.secondary_results

    def get_data(self) -> list[Any]:
        """Get just the data from all results."""
        return [r.data for r in self.all_results()]


class RelevanceEngine:
    """
    Relevance Engine for intelligent result ranking.

    RESPONSIBILITIES:
    1. Filter non-relevant results
    2. Order by relevance
    3. Limit intelligently (not always 10)
    4. Explain why these results

    KEY PRINCIPLE:
    Not just sorting by date or name.
    Understanding WHAT the user is REALLY looking for
    and prioritizing accordingly.
    """

    def __init__(
        self,
        user_memory: UserMemoryService | None = None,
        config: V3RelevanceConfig | None = None,
    ):
        # Load config from factory if not provided
        self._config = config or get_v3_relevance_config()

        # Thresholds from config (for backwards compatibility with existing code)
        self.PRIMARY_THRESHOLD = self._config.primary_threshold
        self.MINIMUM_THRESHOLD = self._config.minimum_threshold

        self._scoring_rules = self._build_scoring_rules()
        self.user_memory = user_memory

    def rank_and_filter(
        self,
        results: list[Any],
        intelligence: QueryIntelligence,
        user_context: UserContext | None = None,
        language: str = DEFAULT_LANGUAGE,
    ) -> FilteredResults:
        """
        Filter and order results by relevance.

        Flow:
        1. Score each result
        2. Filter below threshold
        3. Separate primary/secondary
        4. Limit intelligently

        Args:
            results: List of results to rank
            intelligence: Query intelligence with user goal and intent
            user_context: Optional user context for episodic memory scoring
            language: Language code for i18n messages

        Returns:
            FilteredResults with ranked primary/secondary results
        """
        if not results:
            return FilteredResults(
                primary_results=[],
                secondary_results=[],
                total_found=0,
                total_shown=0,
                filter_explanation=V3Messages.get_filter_explanation(language, 0, 0),
            )

        # Get user context if available
        user_ctx = user_context

        # Score each result
        ranked: list[RankedResult] = []
        for result in results:
            if user_ctx:
                score, reasons = self._score_result_with_context(
                    result, intelligence, user_ctx, language
                )
            else:
                score, reasons = self._score_result(result, intelligence, language)

            # Filter out very low scores
            if score >= self.MINIMUM_THRESHOLD:
                ranked.append(
                    RankedResult(
                        data=result,
                        relevance_score=score,
                        relevance_reasons=reasons,
                    )
                )

        # Sort by relevance
        ranked.sort(key=lambda r: r.relevance_score, reverse=True)

        # Apply smart limit based on user goal
        limit = self._determine_limit(intelligence)
        top_results = ranked[:limit]

        # Mark primary results
        primary = [r for r in top_results if r.relevance_score >= self.PRIMARY_THRESHOLD]
        secondary = [r for r in top_results if r.relevance_score < self.PRIMARY_THRESHOLD]

        for r in primary:
            r.is_primary = True

        # Build explanation (using i18n)
        explanation = self._build_explanation(
            total=len(results),
            shown=len(top_results),
            intelligence=intelligence,
            language=language,
        )

        return FilteredResults(
            primary_results=primary,
            secondary_results=secondary,
            total_found=len(results),
            total_shown=len(top_results),
            filter_explanation=explanation,
        )

    def _score_result(
        self,
        result: Any,
        intelligence: QueryIntelligence,
        language: str = DEFAULT_LANGUAGE,
    ) -> tuple[float, list[str]]:
        """
        Score an individual result.

        Factors:
        1. Match with query
        2. Recency (for certain goals)
        3. Data completeness
        4. Past interactions (if available)

        Uses i18n for multi-language reason messages.
        """
        from src.domains.agents.analysis.query_intelligence import UserGoal

        score = 0.5  # Base score
        reasons = []

        # Get result as dict if possible
        result_dict = self._to_dict(result)
        if not result_dict:
            return score, [V3Messages.get_relevance_reason("unknown_format", language)]

        # === Factor 1: Query match (use english_query for cross-language consistency) ===
        query_terms = intelligence.english_query.lower().split()
        matches = 0
        for term in query_terms:
            if len(term) < 2:  # Skip very short terms
                continue
            for _key, value in result_dict.items():
                if isinstance(value, str) and term in value.lower():
                    matches += 1
                    break

        if matches > 0:
            match_boost = min(0.3, matches * 0.1)
            score += match_boost
            reasons.append(
                V3Messages.get_relevance_reason("matches_terms", language, count=matches)
            )

        # === Factor 2: Recency (for calendar, emails) ===
        if intelligence.primary_domain in ("event", "email"):
            recency = self._check_recency(result_dict)
            if recency == "recent":
                score += 0.2
                reasons.append(V3Messages.get_relevance_reason("recent", language))
            elif recency == "today":
                score += 0.3
                reasons.append(V3Messages.get_relevance_reason("today", language))

        # === Factor 3: Data completeness ===
        completeness = self._data_completeness(result_dict, intelligence.primary_domain)
        if completeness > 0.8:
            score += 0.1
            reasons.append(V3Messages.get_relevance_reason("complete_data", language))

        # === Factor 4: Goal-specific boost ===
        if intelligence.user_goal == UserGoal.COMMUNICATE:
            # Boost results with contact info
            if self._has_contact_info(result_dict):
                score += 0.15
                reasons.append(V3Messages.get_relevance_reason("has_contact_info", language))

        elif intelligence.user_goal == UserGoal.PLAN_ORGANIZE:
            # Boost results with location/time
            if "location" in result_dict or "start" in result_dict:
                score += 0.15
                reasons.append(V3Messages.get_relevance_reason("has_location_time", language))

        return min(1.0, score), reasons

    def _score_result_with_context(
        self,
        result: Any,
        intelligence: QueryIntelligence,
        user_ctx: UserContext,
        language: str = DEFAULT_LANGUAGE,
    ) -> tuple[float, list[str]]:
        """
        Enriched scoring with personal context (Episodic Memory).

        Uses i18n for multi-language reason messages.
        """
        score, reasons = self._score_result(result, intelligence, language)
        result_dict = self._to_dict(result)

        if not result_dict:
            return score, reasons

        # === EPISODIC MEMORY FACTORS ===

        # Factor 5: Geographic proximity
        if user_ctx.home_location:
            location = result_dict.get("location") or result_dict.get("formattedAddress")
            if location and isinstance(location, str):
                proximity = self._calculate_proximity(location, user_ctx.home_location)
                if proximity == "nearby":  # < 10km
                    score += 0.25
                    reasons.append(
                        V3Messages.get_relevance_reason(
                            "nearby", language, location=user_ctx.home_location
                        )
                    )
                elif proximity == "same_city":
                    score += 0.15
                    reasons.append(V3Messages.get_relevance_reason("same_city", language))

        # Factor 6: Work location proximity (for business context)
        if user_ctx.work_location and intelligence.primary_domain in ("place", "event"):
            location = result_dict.get("location") or result_dict.get("formattedAddress")
            if location and isinstance(location, str):
                proximity = self._calculate_proximity(location, user_ctx.work_location)
                if proximity == "nearby":
                    score += 0.2
                    reasons.append(V3Messages.get_relevance_reason("near_work", language))

        # Factor 7: Interaction history
        item_id = result_dict.get("id") or result_dict.get("resourceName")
        if item_id and user_ctx.interaction_history:
            interaction_count = user_ctx.interaction_history.get(str(item_id), 0)
            if interaction_count > 5:
                score += 0.2
                reasons.append(V3Messages.get_relevance_reason("frequent_contact", language))
            elif interaction_count > 0:
                score += 0.1
                reasons.append(V3Messages.get_relevance_reason("already_contacted", language))

        # Factor 8: Preferred place types
        if intelligence.primary_domain == "place":
            place_types = result_dict.get("types", [])
            if user_ctx.preferred_place_types and isinstance(place_types, list):
                if any(t in user_ctx.preferred_place_types for t in place_types):
                    score += 0.15
                    reasons.append(V3Messages.get_relevance_reason("favorite_place_type", language))

        return min(1.0, score), reasons

    def _determine_limit(self, intelligence: QueryIntelligence) -> int:
        """
        Determine number of results to show.

        NOT always 10. Depends on context:
        - Specific search (high confidence) -> 3
        - General search -> 5
        - Exploration -> 10
        """
        from src.domains.agents.analysis.query_intelligence import UserGoal

        # NOTE: "detail" intent removed (2026-01 simplification)
        # Now all retrieval uses "search" with full content always returned

        # If high confidence search, fewer results
        if intelligence.immediate_intent == "search" and intelligence.immediate_confidence > 0.9:
            return 3

        # If exploring, more results
        if intelligence.user_goal == UserGoal.EXPLORE:
            return 10

        # Default based on goal
        GOAL_LIMITS = {
            UserGoal.FIND_INFORMATION: 5,
            UserGoal.COMMUNICATE: 3,
            UserGoal.TAKE_ACTION: 3,
            UserGoal.PLAN_ORGANIZE: 5,
            UserGoal.UNDERSTAND: 7,
            UserGoal.EXPLORE: 10,
        }
        return GOAL_LIMITS.get(intelligence.user_goal, 5)

    def _build_explanation(
        self,
        total: int,
        shown: int,
        intelligence: QueryIntelligence,
        language: str = DEFAULT_LANGUAGE,
    ) -> str:
        """
        Build filtering explanation.

        Uses i18n for multi-language support.
        """
        return V3Messages.get_filter_explanation(
            language=language,
            total=total,
            shown=shown,
            intent=intelligence.immediate_intent,
        )

    def _to_dict(self, result: Any) -> dict | None:
        """Convert result to dict."""
        if isinstance(result, dict):
            return result
        if hasattr(result, "dict"):
            return result.dict()  # type: ignore[no-any-return]
        if hasattr(result, "model_dump"):
            return result.model_dump()  # type: ignore[no-any-return]
        if hasattr(result, "__dict__"):
            return result.__dict__  # type: ignore[no-any-return]
        return None

    def _check_recency(self, result_dict: dict) -> str:
        """Check if result is recent."""
        date_fields = ["start", "date", "created", "modified", "internalDate", "sentAt"]

        for field_name in date_fields:
            if field_name not in result_dict:
                continue

            value = result_dict[field_name]
            if not value:
                continue

            try:
                # Try to parse the date
                if isinstance(value, str):
                    # Handle ISO format
                    if "T" in value:
                        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    else:
                        dt = datetime.fromisoformat(value)
                elif isinstance(value, int | float):
                    # Handle timestamp (milliseconds) - timestamps are always UTC
                    dt = datetime.fromtimestamp(value / 1000 if value > 1e10 else value, tz=UTC)
                else:
                    continue

                now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()

                if dt.date() == now.date():
                    return "today"
                elif (now - dt) < timedelta(days=7):
                    return "recent"

            except (ValueError, TypeError, OSError):
                pass

        return "old"

    def _has_contact_info(self, result_dict: dict) -> bool:
        """Check if result has contact information."""
        contact_fields = [
            "email",
            "emailAddresses",
            "phone",
            "phoneNumbers",
            "mobilePhone",
        ]
        for field_name in contact_fields:
            if field_name in result_dict and result_dict[field_name]:
                return True
        return False

    def _data_completeness(self, result_dict: dict, domain: str) -> float:
        """Calculate data completeness score."""
        REQUIRED_FIELDS = {
            "contacts": ["name", "emailAddresses"],
            "events": ["summary", "start"],
            "emails": ["subject", "from"],
            "tasks": ["title"],
            "places": ["name", "formattedAddress"],
        }

        required = REQUIRED_FIELDS.get(domain, [])
        if not required:
            return 1.0

        present = sum(1 for f in required if f in result_dict and result_dict[f])
        return present / len(required)

    def _calculate_proximity(
        self,
        location: str,
        reference: str,
    ) -> str:
        """
        Calculate proximity between two locations.

        TODO: Implement with real geocoding.
        For now, heuristics on names.
        """
        location_lower = location.lower()
        reference_lower = reference.lower()

        # Same location (exact match)
        if reference_lower in location_lower:
            return "nearby"

        # Same city
        reference_parts = reference_lower.split()
        for part in reference_parts:
            if len(part) > 3 and part in location_lower:
                return "same_city"

        # Known nearby cities (Paris area)
        NEARBY_CITIES = {
            "joinville-le-pont": [
                "saint-maur",
                "champigny",
                "nogent",
                "vincennes",
                "fontenay",
                "le perreux",
            ],
            "saint-maur": [
                "joinville",
                "champigny",
                "creteil",
                "maisons-alfort",
            ],
            "paris": [
                "montreuil",
                "vincennes",
                "boulogne",
                "neuilly",
                "levallois",
                "issy",
            ],
        }

        for city, nearby in NEARBY_CITIES.items():
            if city in reference_lower:
                if any(n in location_lower for n in nearby):
                    return "nearby"

        return "far"

    def _build_scoring_rules(self) -> dict:
        """Build domain-specific scoring rules."""
        return {
            "contacts": {
                "boost_fields": ["name", "email"],
                "recency_matters": False,
            },
            "events": {
                "boost_fields": ["summary", "location"],
                "recency_matters": True,
            },
            "emails": {
                "boost_fields": ["subject", "from"],
                "recency_matters": True,
            },
            "places": {
                "boost_fields": ["name", "formattedAddress"],
                "recency_matters": False,
            },
            "tasks": {
                "boost_fields": ["title"],
                "recency_matters": True,
            },
        }


class UserMemoryService:
    """
    User Memory Service.

    Stores and retrieves personal context:
    - Frequent locations
    - Frequent contacts
    - Learned preferences
    """

    def __init__(self) -> None:
        # In-memory cache for development
        self._contexts: dict[str, UserContext] = {}

    async def get_user_context(self, user_id: str) -> UserContext:
        """Retrieve user context from storage."""
        if user_id in self._contexts:
            return self._contexts[user_id]

        # Return default context
        # In production, this would fetch from PostgreSQL/Redis
        return UserContext.default(user_id)

    async def update_user_context(
        self,
        user_id: str,
        updates: dict[str, Any],
    ) -> UserContext:
        """Update user context with new data."""
        ctx = await self.get_user_context(user_id)

        # Apply updates
        for key, value in updates.items():
            if hasattr(ctx, key):
                setattr(ctx, key, value)

        self._contexts[user_id] = ctx
        return ctx

    async def record_interaction(
        self,
        user_id: str,
        item_id: str,
        interaction_type: str = "view",
    ) -> None:
        """Record an interaction to enrich context."""
        ctx = await self.get_user_context(user_id)

        # Increment interaction counter
        current = ctx.interaction_history.get(item_id, 0)
        ctx.interaction_history[item_id] = current + 1

        self._contexts[user_id] = ctx

    async def add_search(
        self,
        user_id: str,
        query: str,
    ) -> None:
        """Add a search to recent searches."""
        ctx = await self.get_user_context(user_id)

        # Add to recent searches (keep last 20)
        ctx.recent_searches.insert(0, query)
        ctx.recent_searches = ctx.recent_searches[:20]

        self._contexts[user_id] = ctx

    async def set_location(
        self,
        user_id: str,
        location_type: str,
        location: str,
    ) -> None:
        """Set a user's location (home or work)."""
        ctx = await self.get_user_context(user_id)

        if location_type == "home":
            ctx.home_location = location
        elif location_type == "work":
            ctx.work_location = location

        self._contexts[user_id] = ctx


# Singletons
_engine: RelevanceEngine | None = None
_memory_service: UserMemoryService | None = None


def get_relevance_engine(config: V3RelevanceConfig | None = None) -> RelevanceEngine:
    """Get singleton RelevanceEngine instance."""
    global _engine, _memory_service
    if _engine is None:
        _memory_service = get_user_memory_service()
        _engine = RelevanceEngine(
            user_memory=_memory_service,
            config=config or get_v3_relevance_config(),
        )
    return _engine


def get_user_memory_service() -> UserMemoryService:
    """Get singleton UserMemoryService instance."""
    global _memory_service
    if _memory_service is None:
        _memory_service = UserMemoryService()
    return _memory_service


def reset_services() -> None:
    """Reset services for testing."""
    global _engine, _memory_service
    _engine = None
    _memory_service = None
