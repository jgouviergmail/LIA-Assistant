"""
Semantic Tool Selector - Phase 1 of LLM-Native Semantic Architecture.

Selects tools based on semantic similarity between user query and tool descriptions.
Uses embeddings to match queries to tools, replacing keyword-based routing.

Key Features:
- **Max-Pooling Strategy**: Each keyword embedded separately, MAX score used
  - Avoids dilution from averaging multiple keywords into one embedding
  - Query "get my last emails" matches exactly with that keyword → 0.85+
- **Double Threshold Strategy**:
  - Hard threshold (0.70): Direct tool injection
  - Soft threshold (0.60): Uncertainty zone with warning
- **Startup Caching**: Tool embeddings computed once at startup
- **OpenAI Embeddings**: Uses text-embedding-3-small (1536 dims) via TrackedOpenAIEmbeddings
  - Shared singleton with memory store and interest deduplication
  - Token tracking via Prometheus metrics
- **Zero Maintenance i18n**: No keyword lists to maintain per language

Architecture:
    User Query → embed_query() → MAX(cosine_similarity(query, keyword_i)) → sorted(score)
                                                ↓
    Score >= 0.70: Direct inject (high confidence)
    0.60 <= Score < 0.70: Inject with uncertainty flag
    Score < 0.60: Not selected

Max-Pooling vs Average-Pooling:
    Average (old): embed("kw1 | kw2 | kw3") → diluted vector → score ~0.60
    Max-Pool (new): MAX(sim(query, embed(kw1)), sim(query, embed(kw2)), ...) → score ~0.85

References:
    - INTELLIGENCE/PLAN_INITIAL.md: Architecture overview
    - INTELLIGENCE/NOTES_TECHNIQUES.md: Double threshold decision
"""

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from src.domains.agents.registry.catalogue import ToolManifest
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# CONFIGURATION CONSTANTS (defaults, can be overridden via settings)
# =============================================================================

# Legacy thresholds (kept for backwards compatibility, not used in selection)
DEFAULT_HARD_THRESHOLD = 0.70
DEFAULT_SOFT_THRESHOLD = 0.60
DEFAULT_MAX_TOOLS = 8

# Softmax Temperature Calibration (AFTER min-max stretching)
# Pipeline: raw scores → stretch to [0,1] → softmax with temperature
DEFAULT_SOFTMAX_TEMPERATURE = 0.1  # Strong discrimination with stretching
DEFAULT_CALIBRATED_PRIMARY_MIN = 0.15  # Min probability for primary tool

# Hybrid scoring configuration (CORRECTION 7)
DEFAULT_HYBRID_ALPHA = 0.6  # Description weight (keywords = 1 - alpha)
DEFAULT_HYBRID_MODE = "first_line"  # "first_line", "full", "truncate"


# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================


@dataclass
class ToolMatch:
    """A tool matched by semantic similarity."""

    tool_name: str
    tool_manifest: ToolManifest
    score: float  # Calibrated score (softmax-calibrated, probability-like)
    confidence: str = "low"  # "high", "medium", "low"
    # Calibrated threshold
    primary_min: float = DEFAULT_CALIBRATED_PRIMARY_MIN

    def __post_init__(self) -> None:
        # Confidence based on calibrated score
        if self.score >= 0.40:  # 40%+ probability = high confidence
            object.__setattr__(self, "confidence", "high")
        elif self.score >= 0.15:  # 15%+ probability = medium confidence
            object.__setattr__(self, "confidence", "medium")
        else:
            object.__setattr__(self, "confidence", "low")


@dataclass
class ToolSelectionResult:
    """Result of semantic tool selection."""

    selected_tools: list[ToolMatch] = field(default_factory=list)
    top_score: float = 0.0  # Calibrated top score (probability-like)
    has_uncertainty: bool = False
    all_scores: dict[str, float] = field(default_factory=dict)  # Calibrated scores

    @property
    def tool_names(self) -> list[str]:
        """Get list of selected tool names."""
        return [t.tool_name for t in self.selected_tools]

    @property
    def tools_with_scores(self) -> list[dict]:
        """Get tools with scores for debugging."""
        return [
            {
                "tool": t.tool_name,
                "score": round(t.score, 3),
                "confidence": t.confidence,
            }
            for t in self.selected_tools
        ]


# =============================================================================
# SEMANTIC TOOL SELECTOR
# =============================================================================


class SemanticToolSelector:
    """
    Selects tools based on semantic similarity with user queries.

    Uses embeddings to match queries to tool descriptions, enabling
    language-agnostic tool selection without keyword maintenance.

    Singleton pattern for startup caching of tool embeddings.

    Usage:
        # Get singleton instance
        selector = await get_tool_selector()

        # Select tools for query
        result = await selector.select_tools(
            query="cherche les contacts de Jean",
            available_tools=registry.list_tool_manifests()
        )

        # Check results
        for tool in result.selected_tools:
            print(f"{tool.tool_name}: {tool.score:.2f} ({tool.confidence})")
    """

    _instance: "SemanticToolSelector | None" = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __init__(self) -> None:
        """Initialize the selector (use get_tool_selector() instead)."""
        self._embeddings: Any | None = None
        # Max-pooling: store list of embeddings per tool (one per keyword)
        self._tool_keyword_embeddings: dict[str, list[list[float]]] = {}
        # Track which keywords belong to which tool (for debugging)
        self._tool_keywords: dict[str, list[str]] = {}
        self._tool_manifests: dict[str, ToolManifest] = {}
        self._initialized: bool = False
        # Max tools limit
        self._max_tools: int = DEFAULT_MAX_TOOLS
        # Softmax calibration parameters
        self._softmax_temperature: float = DEFAULT_SOFTMAX_TEMPERATURE
        self._calibrated_primary_min: float = DEFAULT_CALIBRATED_PRIMARY_MIN
        # Hybrid scoring (CORRECTION 7: Description + Keywords)
        self._tool_description_embeddings: dict[str, list[float]] = {}
        self._hybrid_alpha: float = DEFAULT_HYBRID_ALPHA
        self._hybrid_mode: str = DEFAULT_HYBRID_MODE
        self._hybrid_enabled: bool = True

    @classmethod
    async def get_instance(cls) -> "SemanticToolSelector":
        """Get or create the singleton instance."""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = SemanticToolSelector()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (for testing)."""
        cls._instance = None

    def _extract_semantic_description(self, description: str) -> str:
        """Extract semantic-relevant portion of tool description for embedding.

        Strategy: First line contains the tool summary (by convention).
        Format: "**Tool: name** - Summary description."

        This avoids embedding technical details (MODES, PARAMETERS, etc.)
        that would dilute the semantic signal.

        Args:
            description: Full tool description string.

        Returns:
            First line (semantic summary) or full description if single line.
        """
        if not description:
            return ""

        # Split on first newline
        first_line = description.split("\n")[0].strip()

        # Remove markdown formatting for cleaner embedding
        # "**Tool: name** - Summary" → "Tool: name - Summary"
        clean_line = re.sub(r"\*\*([^*]+)\*\*", r"\1", first_line)

        return clean_line

    async def initialize(
        self,
        tool_manifests: list[ToolManifest],
        max_tools: int | None = None,
        softmax_temperature: float | None = None,
        calibrated_primary_min: float | None = None,
    ) -> None:
        """
        Initialize the selector with tool manifests.

        Computes and caches embeddings for all tool descriptions.
        Should be called once at application startup.

        Args:
            tool_manifests: List of all available tool manifests
            max_tools: Optional override for max tools to return
            softmax_temperature: Temperature for softmax calibration
            calibrated_primary_min: Min calibrated score for primary tool
        """
        if self._initialized:
            logger.warning("semantic_tool_selector_already_initialized")
            return

        # Load from settings if not provided
        try:
            from src.core.config import get_settings

            settings = get_settings()
            if max_tools is None:
                max_tools = settings.semantic_tool_selector_max_tools
            if softmax_temperature is None:
                softmax_temperature = settings.v3_tool_softmax_temperature
            if calibrated_primary_min is None:
                calibrated_primary_min = settings.v3_tool_calibrated_primary_min
            # CORRECTION 7: Load hybrid scoring settings
            hybrid_alpha = getattr(settings, "v3_tool_selector_hybrid_alpha", None)
            if hybrid_alpha is not None:
                self._hybrid_alpha = hybrid_alpha
            hybrid_mode = getattr(settings, "v3_tool_selector_hybrid_mode", None)
            if hybrid_mode is not None:
                self._hybrid_mode = hybrid_mode
            hybrid_enabled = getattr(settings, "v3_tool_selector_hybrid_enabled", None)
            if hybrid_enabled is not None:
                self._hybrid_enabled = hybrid_enabled
        except Exception:
            pass  # Use defaults if settings not available

        # Apply overrides
        if max_tools is not None:
            self._max_tools = max_tools
        if softmax_temperature is not None:
            self._softmax_temperature = softmax_temperature
        if calibrated_primary_min is not None:
            self._calibrated_primary_min = calibrated_primary_min

        # Initialize embeddings model (OpenAI via shared singleton)
        from src.core.config import settings as app_settings
        from src.infrastructure.llm.memory_embeddings import get_memory_embeddings

        self._embeddings = get_memory_embeddings()
        self._embedding_model_name = app_settings.memory_embedding_model

        # Collect ALL texts for batch embedding (descriptions + keywords)
        all_texts: list[str] = []
        text_metadata: list[tuple[str, str]] = []  # (tool_name, type)

        description_count = 0
        keyword_count = 0
        for manifest in tool_manifests:
            self._tool_manifests[manifest.name] = manifest

            # 1. Description embedding (PRIMARY - semantic context)
            if self._hybrid_enabled:
                desc_semantic = self._extract_semantic_description(manifest.description)
                if desc_semantic:
                    all_texts.append(desc_semantic)
                    text_metadata.append((manifest.name, "description"))
                    description_count += 1

            # 2. Keyword embeddings (REFINEMENT - disambiguation)
            # Keep [manifest.name] fallback: tools without keywords OR description
            # would be invisible to scoring otherwise (score=0 → never selected)
            keywords = manifest.semantic_keywords or [manifest.name]
            self._tool_keywords[manifest.name] = keywords
            keyword_count += len(keywords)
            for keyword in keywords:
                all_texts.append(keyword)
                text_metadata.append((manifest.name, "keyword"))

        logger.info(
            "semantic_tool_selector_initializing",
            tool_count=len(tool_manifests),
            description_count=description_count,
            keyword_count=keyword_count,
            total_embeddings=len(all_texts),
            model=self._embedding_model_name,
            max_tools=self._max_tools,
            softmax_temperature=self._softmax_temperature,
            calibrated_primary_min=self._calibrated_primary_min,
            hybrid_alpha=self._hybrid_alpha,
            hybrid_enabled=self._hybrid_enabled,
            strategy=(
                "hybrid-softmax-calibrated"
                if self._hybrid_enabled
                else "softmax-calibrated-max-pooling"
            ),
        )

        # DEBUG: Log email tool keywords (unified tool)
        if "get_emails_tool" in self._tool_keywords:
            kws = self._tool_keywords["get_emails_tool"]
            logger.info(
                "debug_email_tool_keywords",
                tool_name="get_emails_tool",
                keyword_count=len(kws),
                keywords_preview=kws[:5],
            )

        # Compute embeddings in batch (more efficient than per-keyword)
        try:
            all_embeddings = await self._embeddings.aembed_documents(all_texts)

            # Distribute embeddings by type
            for i, (tool_name, text_type) in enumerate(text_metadata):
                if text_type == "description":
                    self._tool_description_embeddings[tool_name] = all_embeddings[i]
                else:  # keyword
                    if tool_name not in self._tool_keyword_embeddings:
                        self._tool_keyword_embeddings[tool_name] = []
                    self._tool_keyword_embeddings[tool_name].append(all_embeddings[i])

            self._initialized = True

            logger.info(
                "semantic_tool_selector_initialized",
                tool_count=len(tool_manifests),
                total_embeddings=len(all_embeddings),
                tools_with_descriptions=len(self._tool_description_embeddings),
                tools_with_keywords=len(self._tool_keyword_embeddings),
            )

        except Exception as e:
            logger.error(
                "semantic_tool_selector_initialization_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    async def select_tools(
        self,
        query: str,
        available_tools: list[ToolManifest] | None = None,
        max_results: int | None = None,
        include_context_utilities: bool = True,
        extra_embeddings: dict[str, dict] | None = None,
    ) -> ToolSelectionResult:
        """
        Select tools matching the user query.

        Uses semantic similarity with configurable double threshold:
        - score >= hard_threshold: High confidence match
        - soft_threshold <= score < hard_threshold: Medium confidence (uncertainty zone)
        - score < soft_threshold: Not selected

        Args:
            query: User query to match
            available_tools: Optional filter to specific tools
            max_results: Maximum tools to return (default: from settings)
            include_context_utilities: If True, include utility tools when
                top score < 0.85 (prevents over-specificity)
            extra_embeddings: Per-request pre-computed embeddings (e.g., user MCP tools).
                Dict keyed by adapter tool name with "description" (vector) and
                "keywords" (list of vectors) sub-keys. Used as fallback when the
                tool is not found in the singleton's startup-computed caches.

        Returns:
            ToolSelectionResult with matched tools and scores
        """
        if not self._initialized or not self._embeddings:
            raise RuntimeError("SemanticToolSelector not initialized. Call initialize() first.")

        # Use configured max_tools if not overridden
        max_results = max_results or self._max_tools

        # Embed the query
        query_embedding = await self._embeddings.aembed_query(query)

        # Determine which tools to compare against
        if available_tools:
            tool_names = [t.name for t in available_tools]
        else:
            tool_names = list(self._tool_keyword_embeddings.keys())

        # Calculate scores: HYBRID (desc+kw) if enabled, else KEYWORDS-ONLY (legacy)
        from src.infrastructure.llm.local_embeddings import cosine_similarity

        scores: dict[str, float] = {}
        scoring_details: dict[str, dict] = {}  # For debugging

        for name in tool_names:
            desc_score = 0.0
            keyword_score = 0.0
            best_kw = ""

            # Description score (primary) - ONLY if hybrid enabled
            # Check singleton cache first, then per-request extra_embeddings
            if self._hybrid_enabled and name in self._tool_description_embeddings:
                desc_embedding = self._tool_description_embeddings[name]
                desc_score = cosine_similarity(query_embedding, desc_embedding)
            elif self._hybrid_enabled and extra_embeddings and name in extra_embeddings:
                desc_emb = extra_embeddings[name].get("description")
                if desc_emb:
                    desc_score = cosine_similarity(query_embedding, desc_emb)

            # Keyword max-pool score (refinement)
            # Check singleton cache first, then per-request extra_embeddings
            if name in self._tool_keyword_embeddings:
                keyword_embeddings = self._tool_keyword_embeddings[name]
                keywords = self._tool_keywords.get(name, [])

                for i, kw_embedding in enumerate(keyword_embeddings):
                    sim = cosine_similarity(query_embedding, kw_embedding)
                    if sim > keyword_score:
                        keyword_score = sim
                        best_kw = keywords[i] if i < len(keywords) else f"keyword_{i}"
            elif extra_embeddings and name in extra_embeddings:
                extra_kw_embeddings = extra_embeddings[name].get("keywords", [])
                extra_kw_names = extra_embeddings[name].get("keyword_names", [])
                for i, kw_emb in enumerate(extra_kw_embeddings):
                    sim = cosine_similarity(query_embedding, kw_emb)
                    if sim > keyword_score:
                        keyword_score = sim
                        best_kw = extra_kw_names[i] if i < len(extra_kw_names) else f"keyword_{i}"

            # Hybrid combination
            if desc_score > 0 and keyword_score > 0:
                # Both available: weighted combination
                final_score = (
                    self._hybrid_alpha * desc_score + (1 - self._hybrid_alpha) * keyword_score
                )
            elif desc_score > 0:
                # Description only (no keywords defined)
                final_score = desc_score
            elif keyword_score > 0:
                # Keywords only (legacy behavior for tools without description)
                final_score = keyword_score
            else:
                final_score = 0.0

            scores[name] = final_score
            scoring_details[name] = {
                "desc_score": round(desc_score, 3),
                "keyword_score": round(keyword_score, 3),
                "best_keyword": best_kw,
                "final_score": round(final_score, 3),
                "mode": (
                    "hybrid"
                    if desc_score > 0 and keyword_score > 0
                    else ("desc" if desc_score > 0 else "kw")
                ),
            }

        # Apply softmax calibration to amplify score differences
        calibrated_scores = self._apply_softmax_calibration(scores)

        # Sort by CALIBRATED score descending (for selection)
        sorted_tools = sorted(calibrated_scores.items(), key=lambda x: x[1], reverse=True)
        top_calibrated_score = sorted_tools[0][1] if sorted_tools else 0.0

        # Apply calibrated threshold filtering:
        # Only keep tools with calibrated_score > calibrated_primary_min (strictly greater)
        selected: list[ToolMatch] = []
        has_uncertainty = False

        for name, calibrated_score in sorted_tools[:max_results]:
            # Filter: only tools with score strictly > threshold
            if calibrated_score <= self._calibrated_primary_min:
                continue

            # Get manifest from cache or available_tools
            manifest = self._get_manifest(name, available_tools)
            if manifest:
                match = ToolMatch(
                    tool_name=name,
                    tool_manifest=manifest,
                    score=calibrated_score,  # Use calibrated score
                    primary_min=self._calibrated_primary_min,
                )
                selected.append(match)

                # Track uncertainty if calibrated score is low
                if calibrated_score < 0.40:  # Less than 40% probability = uncertainty
                    has_uncertainty = True

        result = ToolSelectionResult(
            selected_tools=selected,
            top_score=top_calibrated_score,
            has_uncertainty=has_uncertainty,
            all_scores=calibrated_scores,  # Return calibrated scores
        )

        # Log selection with hybrid scoring info
        logger.info(
            "semantic_tool_selection_complete",
            query_preview=query[:100],
            selected_count=len(selected),
            top_calibrated_score=round(top_calibrated_score, 3),
            softmax_temperature=self._softmax_temperature,
            hybrid_alpha=self._hybrid_alpha,
            hybrid_enabled=self._hybrid_enabled,
            has_uncertainty=has_uncertainty,
            top_tools=[
                {
                    "tool": t.tool_name,
                    "score": round(t.score, 3),
                    "details": scoring_details.get(t.tool_name, {}),
                }
                for t in selected[:3]
            ],
            all_calibrated_top5=[
                (name, round(calibrated_scores.get(name, 0), 3)) for name, _ in sorted_tools[:5]
            ],
        )

        return result

    def _get_manifest(
        self, tool_name: str, available_tools: list[ToolManifest] | None = None
    ) -> ToolManifest | None:
        """
        Get manifest by name from available tools or cached manifests.

        Args:
            tool_name: Tool name to look up
            available_tools: Optional list to search first

        Returns:
            ToolManifest if found, None otherwise
        """
        # First check available_tools if provided
        if available_tools:
            for t in available_tools:
                if t.name == tool_name:
                    return t
        # Fallback to cached manifests
        return self._tool_manifests.get(tool_name)

    def _apply_softmax_calibration(
        self,
        raw_scores: dict[str, float],
        temperature: float | None = None,
    ) -> dict[str, float]:
        """
        Apply min-max stretching + softmax to calibrate raw cosine similarity scores.

        Two-stage calibration for maximum discrimination:
        1. Min-max stretching: [0.65, 0.70] → [0.0, 1.0] (amplifies relative differences)
        2. Softmax with temperature: [0.0, 1.0] → probability distribution

        Args:
            raw_scores: Dict of tool_name -> raw cosine similarity score
            temperature: Softmax temperature (lower = sharper). Uses instance default if None.

        Returns:
            Dict of tool_name -> calibrated probability-like score (sum to 1.0)
        """
        if not raw_scores:
            return {}

        if len(raw_scores) == 1:
            # Single tool = 100% probability
            return {list(raw_scores.keys())[0]: 1.0}

        temp = temperature if temperature is not None else self._softmax_temperature

        # Convert to numpy for stable computation
        tool_names = list(raw_scores.keys())
        scores_array = np.array([raw_scores[name] for name in tool_names])

        # STAGE 1: Min-Max Stretching
        min_score = np.min(scores_array)
        max_score = np.max(scores_array)
        score_range = max_score - min_score

        if score_range < 1e-6:
            # All scores identical - uniform distribution
            uniform_prob = 1.0 / len(tool_names)
            return dict.fromkeys(tool_names, uniform_prob)

        # Stretch to [0, 1] range
        stretched = (scores_array - min_score) / score_range

        # STAGE 2: Softmax with Temperature
        scaled = stretched / temp
        scaled_shifted = scaled - np.max(scaled)  # Prevent overflow
        exp_scores = np.exp(scaled_shifted)

        # Normalize to get probabilities
        softmax_scores = exp_scores / np.sum(exp_scores)

        return {name: float(softmax_scores[i]) for i, name in enumerate(tool_names)}

    def get_cached_tools(self) -> list[str]:
        """Get list of cached tool names."""
        return list(self._tool_keyword_embeddings.keys())

    def is_initialized(self) -> bool:
        """Check if selector is initialized."""
        return self._initialized


# =============================================================================
# SINGLETON ACCESSOR
# =============================================================================


async def get_tool_selector() -> SemanticToolSelector:
    """
    Get the singleton SemanticToolSelector instance.

    Returns:
        Initialized SemanticToolSelector instance

    Usage:
        selector = await get_tool_selector()
        result = await selector.select_tools(query, available_tools)
    """
    return await SemanticToolSelector.get_instance()


async def initialize_tool_selector(tool_manifests: list[ToolManifest]) -> SemanticToolSelector:
    """
    Initialize the tool selector with manifests.

    Should be called once at application startup.

    Args:
        tool_manifests: All available tool manifests

    Returns:
        Initialized SemanticToolSelector instance
    """
    selector = await get_tool_selector()
    await selector.initialize(tool_manifests)
    return selector


def reset_tool_selector() -> None:
    """Reset the singleton (for testing)."""
    SemanticToolSelector.reset_instance()


# =============================================================================
# USER MCP EMBEDDING COMPUTATION
# =============================================================================


async def compute_tool_embeddings(
    tool_metadata: list[dict[str, Any]],
    server_name: str,
) -> dict[str, dict[str, Any]]:
    """
    Compute E5 embeddings for MCP tool metadata (description + keywords).

    Called at MCP server registration (test_connection) to pre-compute embeddings
    that will be loaded at request time for semantic scoring.

    Reuses the SemanticToolSelector's loaded E5 model. Same pattern as
    SemanticToolSelector.initialize() for native tools:
    - Description: first line cleaned (via _extract_semantic_description logic)
    - Keywords: [server_name, tool_name, *description_words]

    Args:
        tool_metadata: List of {"name": str, "description": str, ...}
        server_name: Server name (used as keyword for domain signal)

    Returns:
        Dict keyed by raw MCP tool_name with "description" (vector) and
        "keywords" (list of vectors) sub-keys. Re-keyed to adapter names
        at request time (see user_context.py setup_user_mcp_tools).
    """
    selector = await get_tool_selector()
    if not selector._initialized or not selector._embeddings:
        logger.warning(
            "compute_tool_embeddings_skipped",
            reason="selector_not_initialized",
        )
        return {}

    embeddings_model = selector._embeddings
    result: dict[str, dict[str, Any]] = {}

    all_texts: list[str] = []
    text_metadata: list[tuple[str, str]] = []  # (tool_name, "description"|"keyword")
    keyword_map: dict[str, list[str]] = {}

    for tool in tool_metadata:
        name = tool.get("name", "")
        desc = tool.get("description", "")

        # Description embedding (first line, cleaned — same as _extract_semantic_description)
        if desc:
            first_line = desc.split("\n")[0].strip()
            clean_line = re.sub(r"\*\*([^*]+)\*\*", r"\1", first_line)
            if clean_line:
                all_texts.append(clean_line)
                text_metadata.append((name, "description"))

        # Keyword embeddings — same pattern as initialize() semantic_keywords
        desc_words = [w.strip(".,;:!?") for w in desc.split() if len(w.strip(".,;:!?")) > 3]
        keywords = [server_name, name, *desc_words[:10]]
        keyword_map[name] = keywords
        for kw in keywords:
            all_texts.append(kw)
            text_metadata.append((name, "keyword"))

    if not all_texts:
        return {}

    # Batch embed (efficient — single model call for all texts)
    all_embeddings = await embeddings_model.aembed_documents(all_texts)

    # Distribute embeddings by tool and type
    for i, (tool_name, text_type) in enumerate(text_metadata):
        if tool_name not in result:
            result[tool_name] = {}
        if text_type == "description":
            result[tool_name]["description"] = all_embeddings[i]
        else:
            if "keywords" not in result[tool_name]:
                result[tool_name]["keywords"] = []
            result[tool_name]["keywords"].append(all_embeddings[i])

    # Add keyword names for debugging/traceability
    for tool_name, keywords in keyword_map.items():
        if tool_name in result:
            result[tool_name]["keyword_names"] = keywords

    logger.info(
        "tool_embeddings_computed",
        server_name=server_name,
        tool_count=len(tool_metadata),
        embedded_tools=len(result),
        total_vectors=len(all_embeddings),
    )

    return result


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "SemanticToolSelector",
    "ToolMatch",
    "ToolSelectionResult",
    "get_tool_selector",
    "initialize_tool_selector",
    "reset_tool_selector",
    "compute_tool_embeddings",
    "DEFAULT_MAX_TOOLS",
    "DEFAULT_SOFTMAX_TEMPERATURE",
    "DEFAULT_CALIBRATED_PRIMARY_MIN",
    "DEFAULT_HYBRID_ALPHA",
    "DEFAULT_HYBRID_MODE",
]
