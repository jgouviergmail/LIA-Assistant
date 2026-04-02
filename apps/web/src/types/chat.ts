/**
 * Chat types for LIA AI Assistant
 */

export type MessageRole = 'user' | 'assistant' | 'system';

/**
 * Attachment metadata stored in message.metadata.attachments.
 * Used for rendering attachment thumbnails in chat messages.
 */
export interface MessageAttachmentMeta {
  id: string;
  filename: string;
  mime_type: string;
  size: number;
  content_type: 'image' | 'document';
  /** Client-side Object URL for immediate preview (available during send, absent on reload). */
  previewUrl?: string;
}

export interface Message {
  id: string;
  content: string;
  role: MessageRole;
  timestamp: Date;
  avatar?: string;
  // Token usage metadata (only for assistant messages)
  tokensIn?: number;
  tokensOut?: number;
  tokensCache?: number;
  costEur?: number;
  googleApiRequests?: number;
  // Skill activation metadata (only for assistant messages)
  skillName?: string;
  // AI-generated images (only for assistant messages with image generation)
  generatedImages?: { url: string; alt: string }[];
  // Browser screenshot card (only for assistant messages with browser automation)
  browserScreenshot?: { url: string; alt: string };
  // Voice input metadata (only for user messages)
  source?: 'text' | 'voice';
  audioDurationSeconds?: number;
  // Message metadata (HITL responses, run_id, etc.)
  metadata?: Record<string, unknown>;
}

// SSE (Server-Sent Events) types
export type SSEStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

export type SSEChunkType =
  | 'token'
  | 'router_decision'
  | 'planner_metadata'
  | 'error'
  | 'done'
  | 'hitl_interrupt'
  // HITL Streaming (Phase 4): Progressive question rendering
  | 'hitl_interrupt_metadata'
  | 'hitl_question_token'
  | 'hitl_clarification_token'
  | 'hitl_rejection_token'
  | 'hitl_interrupt_complete'
  // Phase 5: Orchestration types
  | 'node'
  | 'tool_call'
  | 'tool_result'
  | 'metadata'
  | 'content'
  // Phase 5.5: Post-processing streaming (photo HTML injection, etc.)
  | 'content_replacement'
  // Phase 6: Execution step tracking (generic node/tool display)
  | 'execution_step'
  // LARS: Registry-First Architecture (side-channel data)
  | 'registry_update'
  // Debug Panel: Scoring metrics for threshold tuning (DEBUG=true only)
  | 'debug_metrics'
  | 'debug_metrics_update'
  // Voice TTS: Voice comment audio streaming
  | 'voice_comment_start'
  | 'voice_audio_chunk'
  | 'voice_complete'
  | 'voice_error'
  // Browser screenshots: progressive screenshot overlay
  | 'browser_screenshot';

export interface ChatStreamChunk {
  type: SSEChunkType;
  content: string;
  metadata?:
    | RouterMetadata
    | PlannerMetadata
    | DoneMetadata
    | ToolApprovalMetadata
    | OrchestrationMetadata
    | RegistryUpdateMetadata
    | DebugMetricsMetadata
    | Record<string, unknown>
    | null;
  // Phase 5: Additional fields for orchestration
  node_name?: string;
  tool_name?: string;
  args?: Record<string, unknown>;
  success?: boolean;
  error?: string;
  error_code?: string;
}

export interface DoneMetadata {
  duration_ms?: number;
  total_tokens?: number;
  // Token tracking metadata
  tokens_in?: number;
  tokens_out?: number;
  tokens_cache?: number;
  cost_eur?: number;
  message_count?: number;
  google_api_requests?: number;
  // Skill activation
  skill_name?: string;
  // AI-generated images
  generated_images?: { url: string; alt: string }[];
  // Browser screenshot card
  browser_screenshot?: { url: string; alt: string };
  // Psyche Engine: mood state summary from post-response processing
  psyche_state?: {
    mood_label: string;
    mood_color: string;
    mood_pleasure: number;
    mood_arousal: number;
    mood_dominance: number;
    active_emotion: string | null;
    emotion_intensity: number;
    relationship_stage: string;
  };
}

export interface RouterMetadata {
  intention: string;
  confidence: number;
  context_label: string;
  next_node: string;
  reasoning?: string | null;
  router_decision?: {
    intention: string;
    confidence: number;
    selected_agent: string;
  };
}

// Phase 5: Orchestration metadata types
export interface PlannerMetadata {
  step: string;
  is_valid?: boolean;
  total_cost_usd?: number;
  step_count?: number;
  agent_name?: string;
  plan_generated?: boolean;
}

export interface OrchestrationMetadata {
  step?: string; // 'plan_validation' | 'plan_execution' | 'orchestrator'
  is_valid?: boolean;
  total_cost_usd?: number;
  step_count?: number;
  current_step?: number;
  total_steps?: number;
  agent_name?: string;
  plan_generated?: boolean;
  router_decision?: {
    intention: string;
    confidence: number;
    selected_agent: string;
  };
}

// Phase 6: Execution step tracking metadata
export interface ExecutionStepMetadata {
  type: 'execution_step';
  step_type: 'tool' | 'node';
  step_name: string;
  status: 'started' | 'completed' | 'failed';
  emoji: string;
  i18n_key: string;
  category: 'system' | 'agent' | 'tool' | 'context';
}

// === LARS: Registry-First Architecture Types ===

/**
 * RegistryItemType - Types of items stored in LARS registry
 * Maps to backend RegistryItemType enum
 */
export type RegistryItemType =
  | 'CONTACT'
  | 'EMAIL'
  | 'EVENT'
  | 'DRAFT'
  | 'CHART'
  | 'FILE'
  | 'TASK'
  | 'NOTE'
  | 'CALENDAR_SLOT'
  | 'ROUTE'
  | 'MCP_APP';

/**
 * RegistryItemMeta - Metadata for registry items
 */
export interface RegistryItemMeta {
  source: string; // Data source (e.g., "google_contacts")
  domain?: string; // Domain name (e.g., "contacts")
  tool_name?: string; // Tool that created this item
  step_id?: string; // Execution step ID
  ttl_seconds?: number; // Time-to-live in seconds
  timestamp: string; // ISO timestamp
}

/**
 * RegistryItem - Single item in LARS registry
 * Frontend resolves IDs in LLM content to these items
 */
export interface RegistryItem {
  id: string; // Unique ID (e.g., "contact_abc123")
  type: RegistryItemType; // Item type
  payload: Record<string, unknown>; // Actual data (contact details, email content, etc.)
  meta: RegistryItemMeta; // Metadata
}

/**
 * RegistryUpdateMetadata - SSE metadata for registry_update events
 * Sent BEFORE tokens to ensure frontend has data to resolve IDs
 */
export interface RegistryUpdateMetadata {
  items: Record<string, RegistryItem>; // Map of id → RegistryItem
  count: number; // Number of items in this update
}

// === HITL (Human-in-the-Loop) Tool Approval Types ===
// Aligned with LangChain v1.0 HumanInTheLoopMiddleware format

/**
 * ActionRequest - Format from LangChain v1.0 HumanInTheLoopMiddleware
 * This is the official structure sent by the middleware when a tool requires approval
 */
export interface ActionRequest {
  name: string; // Tool name (e.g., "search_contacts_tool")
  args: Record<string, unknown>; // Tool arguments (renamed from 'arguments' for clarity)
  description: string; // Description of what the tool does
  // Note: The backend sends 'arguments' but we rename to 'args' for consistency
}

/**
 * ReviewConfig - Configuration for how to handle approval decisions
 * From LangChain v1.0 HumanInTheLoopMiddleware
 */
export interface ReviewConfig {
  action_name: string; // Tool name being reviewed
  allowed_decisions: ('approve' | 'edit' | 'reject')[]; // Allowed decision types
}

/**
 * ToolApprovalMetadata - SSE metadata payload from backend
 * Contains action_requests and review_configs from HumanInTheLoopMiddleware
 */
export interface ToolApprovalMetadata {
  type: 'tool_approval_request';
  action_requests: ActionRequest[]; // LangChain v1.0 format
  review_configs: ReviewConfig[]; // LangChain v1.0 format
  count?: number; // Optional count for convenience
  message_id?: string; // HITL Streaming: message ID for tracking
  generated_question?: string; // HITL Streaming: fallback question if streaming fails
}

/**
 * Browser geolocation data sent with chat requests.
 * Automatically captured when user grants permission.
 */
export interface BrowserGeolocation {
  lat: number;
  lon: number;
  accuracy?: number | null;
  timestamp?: number | null;
}

/**
 * Browser context data sent with chat requests.
 * Contains optional browser-side information that enriches the request.
 */
export interface BrowserContext {
  geolocation?: BrowserGeolocation | null;
  /** LIA avatar gender preference: 'male' or 'female' (affects TTS voice) */
  lia_gender?: 'male' | 'female' | null;
  /** Screen width in pixels for responsive rendering */
  viewport_width?: number | null;
}

export interface ChatRequest {
  message: string;
  user_id: string;
  session_id: string;
  context?: BrowserContext | null;
  /** IDs of uploaded file attachments to include in this message */
  attachment_ids?: string[] | null;
}

// === Voice TTS Types ===

/**
 * VoiceAudioChunk - Audio chunk for voice comment streaming.
 * Contains base64-encoded audio data and metadata for playback.
 */
/**
 * BrowserScreenshotData - Progressive screenshot data from browser automation.
 * Sent via SSE during browsing to show real-time page captures.
 */
export interface BrowserScreenshotData {
  image_base64: string;
  url: string;
  title: string;
}

export interface VoiceAudioChunk {
  audio_base64: string; // Base64-encoded audio data (MP3)
  phrase_index: number; // Index of the phrase (0-based)
  phrase_text?: string; // Text of the phrase (for debugging)
  is_last: boolean; // True if this is the last audio chunk
  duration_ms?: number | null; // Estimated duration in milliseconds
  mime_type: string; // MIME type (default: "audio/mpeg")
}

/**
 * VoiceMetadata - SSE metadata for voice events.
 */
export interface VoiceMetadata {
  run_id?: string;
  chunk_count?: number;
  error_type?: string;
}

// === Debug Panel Types (DEBUG=true only) ===

/**
 * ThresholdCheck - Comparison between actual value and threshold
 */
export interface ThresholdCheck {
  value: number; // Configured threshold
  actual: number; // Measured value
  passed: boolean; // Whether actual >= threshold
}

/**
 * ThresholdInfo - Informational threshold (no pass/fail)
 */
export interface ThresholdInfo {
  value: number | string;
  info: string; // Description of what this threshold does
}

/**
 * IntentDetectionMetrics - Intent detection step metrics
 */
export interface IntentDetectionMetrics {
  detected_intent: string;
  confidence: number;
  user_goal: string;
  goal_reasoning: string;
  thresholds: {
    high_threshold: ThresholdCheck;
    fallback_threshold: ThresholdCheck;
  };
}

/**
 * DomainSelectionMetrics - Domain selection step metrics
 *
 * v3.1 LLM-based: The LLM selects domains with a single confidence score.
 * No more CAL/RAW distinction (legacy embeddings + softmax concept).
 */
export interface DomainSelectionMetrics {
  selected_domains: string[];
  primary_domain: string;
  /** LLM confidence score (applied to all selected domains) */
  top_score: number;
  /** Domain confidence scores (all domains have same LLM confidence) */
  all_scores: Record<string, number>;
  thresholds: {
    /** Minimum confidence to accept domain selection */
    primary_min?: ThresholdCheck;
    /** Maximum number of domains to select */
    max_domains?: ThresholdInfo;
  };
}

/**
 * RoutingDecisionMetrics - Routing decision step metrics
 */
export interface RoutingDecisionMetrics {
  route_to: string;
  confidence: number;
  bypass_llm: boolean;
  reasoning_trace: string[];
  thresholds: {
    chat_semantic_threshold: ThresholdCheck;
    high_semantic_threshold: ThresholdCheck;
    min_confidence: ThresholdCheck;
    chat_override_threshold: ThresholdInfo;
  };
}

/**
 * ContextResolutionMetrics - Context resolution step metrics
 */
export interface ContextResolutionMetrics {
  turn_type: string;
  is_reference: boolean;
  source_turn_id: number | null;
  source_domain: string | null;
  resolved_references: Record<string, string> | null;
  thresholds: {
    confidence_threshold: ThresholdInfo;
    active_window_turns: ThresholdInfo;
  };
}

/**
 * QueryInfoMetrics - Query information metrics
 */
export interface QueryInfoMetrics {
  original_query: string;
  english_query: string;
  english_enriched_query: string | null;
  user_language: string;
  // Optional dead code fields (always [] from backend, kept for backward compat)
  implicit_intents?: string[];
  anticipated_needs?: string[];
  fallback_strategies?: string[];
}

/**
 * ForEachAnalysis - FOR_EACH pattern detection metrics (v3.1)
 * Bulk operation analysis for queries like "send email to ALL contacts"
 */
export interface ForEachAnalysis {
  detected: boolean;
  collection_key: string | null;
  cardinality_magnitude: number | null;
  cardinality_mode: 'single' | 'multiple' | 'all' | 'each';
  constraint_hints: Record<string, boolean>;
}

/**
 * ExecutionWave - A single wave of parallel execution
 */
export interface ExecutionWave {
  wave_id: number;
  steps: string[];
  size: number;
}

/**
 * ExecutionWavesInfo - Parallel execution wave analysis
 */
export interface ExecutionWavesInfo {
  total_waves: number;
  max_parallelism: number;
  critical_path_length: number;
  waves: ExecutionWave[];
  average_parallelism: number;
}

/**
 * LifecycleNode - A node in the request lifecycle pipeline
 */
export interface LifecycleNode {
  name: string;
  status: 'completed';
  tokens_in: number;
  tokens_out: number;
  tokens_cache: number;
  cost_eur: number;
  calls_count: number;
  /** v3.2: Execution time in milliseconds */
  duration_ms: number;
}

/**
 * RequestLifecycleMetrics - Request lifecycle through LangGraph nodes
 */
export interface RequestLifecycleMetrics {
  nodes: LifecycleNode[];
  total_nodes: number;
  /** v3.2: Total LLM execution time in milliseconds */
  total_duration_ms?: number;
}

/**
 * ToolMatch - A tool matched by semantic similarity
 */
export interface ToolMatch {
  tool_name: string;
  score: number;
  confidence: 'high' | 'medium' | 'low';
}

/**
 * ToolSelectionMetrics - Tool selection step metrics
 *
 * v3.1 LLM-based: The planner selects tools directly.
 */
export interface ToolSelectionMetrics {
  selected_tools: ToolMatch[];
  /** Top tool score */
  top_score: number;
  has_uncertainty: boolean;
  /** All tool scores */
  all_scores: Record<string, number>;
  thresholds: {
    /** Minimum score to select a tool */
    primary_min?: ThresholdCheck;
    /** Maximum number of tools to include */
    max_tools?: ThresholdInfo;
  };
}

/**
 * TokenBudget - Token context budget metrics
 * v3.1: Added real consumption fields (total_consumed, tokens_input/output/cache)
 */
export interface TokenBudget {
  /** Context size in tokens (for zone calculation) */
  current_tokens: number;
  thresholds: {
    safe: number;
    warning: number;
    critical: number;
    max: number;
  };
  zone: 'safe' | 'warning' | 'critical' | 'emergency';
  strategy: string;
  fallback_active: boolean;
  // v3.1: Real token consumption from LLM calls (response included)
  /** Total tokens consumed (input + output) - real value from LLM calls */
  total_consumed?: number;
  /** Total input tokens from all LLM calls */
  tokens_input?: number;
  /** Total output tokens from all LLM calls */
  tokens_output?: number;
  /** Total cached tokens (prompt cache hits) */
  tokens_cache?: number;
}

/**
 * ExecutionStep - Single step in execution timeline
 */
export interface ExecutionStep {
  step_id: string;
  tool_name: string;
  domain: string;
  status: 'pending' | 'completed' | 'error';
  success?: boolean | null;
  duration_ms?: number | null;
}

/**
 * ExecutionTimeline - Execution timeline with step details
 */
export interface ExecutionTimeline {
  steps: ExecutionStep[];
  total_steps: number;
  completed_steps: number;
}

/**
 * PlannerIntelligence - Planner strategy and efficiency metrics
 */
export interface PlannerIntelligence {
  strategy: 'template_bypass' | 'filtered_catalogue' | 'generative' | 'panic_mode';
  tokens: {
    used: number;
    saved: number;
    full_catalogue_estimate: number;
    reduction_percentage: number;
  };
  plan: {
    steps_count?: number;
    tools_used?: string[];
    estimated_cost_usd?: number | null;
  };
  flags: {
    used_template: boolean;
    used_panic_mode: boolean;
    used_generative: boolean;
  };
  success: boolean;
  error?: string | null;
}

/**
 * LLMCall - Single LLM call with token breakdown
 * Used for detailed per-node token tracking in debug panel
 */
export interface LLMCall {
  node_name: string; // LangGraph node (router, planner, response, etc.)
  model_name: string; // LLM model used (gpt-4.1-mini, etc.)
  tokens_in: number; // Prompt/input tokens
  tokens_out: number; // Completion/output tokens
  tokens_cache: number; // Cached input tokens
  cost_eur: number; // Cost in EUR for this call
  duration_ms?: number; // v3.2: LLM call duration in milliseconds
  call_type?: 'chat' | 'embedding'; // v3.3: Type of LLM call
  sequence?: number; // v3.3: Chronological order number
}

/**
 * LLMSummary - Aggregated summary of all LLM calls
 */
export interface LLMSummary {
  total_calls: number;
  total_tokens_in: number;
  total_tokens_out: number;
  total_tokens_cache: number;
  total_cost_eur: number;
}

/**
 * LLMPipelineMetrics - Chronological reconciliation of ALL LLM calls (v3.3)
 * Provides a unified view of chat + embedding calls sorted by execution order
 */
export interface LLMPipelineMetrics {
  calls: LLMCall[]; // All calls sorted by sequence
  total_calls: number;
  total_chat_calls: number;
  total_embedding_calls: number;
  total_duration_ms: number;
  total_tokens_in: number;
  total_tokens_out: number;
  total_tokens_cache: number;
  total_cost_eur: number;
}

/**
 * GoogleApiCall - Individual Google API call details for debug panel
 */
export interface GoogleApiCall {
  api_name: string; // API identifier (places, routes, geocoding, static_maps)
  endpoint: string; // Endpoint path (e.g., /places:searchText)
  cost_usd: number; // Cost in USD for this call
  cost_eur: number; // Cost in EUR for this call
  cached: boolean; // Whether result was served from cache
}

/**
 * GoogleApiSummary - Aggregated summary of all Google API calls
 */
export interface GoogleApiSummary {
  total_calls: number;
  billable_calls: number;
  cached_calls: number;
  total_cost_usd: number;
  total_cost_eur: number;
}

/**
 * MemoryResolution - Memory resolution mechanism data
 */
export interface MemoryResolution {
  applied: boolean;
  original_query: string;
  enriched_query: string;
  mappings: Record<string, string>; // e.g., {"mes": "Jérôme dupond"}
  num_references: number;
}

/**
 * SemanticPivot - Semantic pivot (translation) mechanism data
 */
export interface SemanticPivot {
  applied: boolean;
  source_language: string;
  original_query: string;
  translated_query: string;
}

/**
 * SemanticExpansion - Semantic expansion mechanism data
 */
export interface SemanticExpansion {
  applied: boolean;
  original_domains: string[];
  expanded_domains: string[];
  added_domains: string[];
  reasons: string[];
  has_person_reference: boolean;
}

/**
 * ChatOverride - Chat override mechanism data
 */
export interface ChatOverride {
  applied: boolean;
  original_domains: string[];
  original_top_score?: number; // Optional in v3.1 (LLM-based doesn't have this)
  intent_confidence?: number; // Optional in v3.1
  confidence?: number; // v3.1: LLM confidence
  intent?: string; // v3.1: LLM intent (action/conversation)
  override_threshold: number;
  reason: string;
}

/**
 * LLMQueryAnalysis - v3.1 LLM-based query analysis mechanism data
 * Replaces SemanticIntentDetector + SemanticDomainSelector + SemanticPivot
 */
export interface LLMQueryAnalysis {
  applied: boolean;
  intent: string; // "action" or "conversation"
  mapped_intent: string; // Internal intent: search, create, update, delete, send, chat
  primary_domain: string | null;
  secondary_domains: string[];
  confidence: number;
  english_query: string;
  reasoning: string; // LLM's brief reasoning (max 20 words)
}

/**
 * ResolvedReference - A reference resolved by the LLM
 * v3.1: Part of LLM query analysis
 */
export interface ResolvedReference {
  original: string;
  resolved: string;
  type: string; // "temporal", "person", "contextual"
}

/**
 * IntelligentMechanisms - All intelligent mechanisms tracking
 */
export interface IntelligentMechanisms {
  // v3.1: LLM-based query analysis (primary mechanism)
  llm_query_analysis?: LLMQueryAnalysis;
  // Memory resolution (now from LLM in v3.1)
  memory_resolution?: MemoryResolution & {
    // v3.1: LLM returns resolved_references instead of mappings
    resolved_references?: ResolvedReference[];
  };
  // Legacy v3.0 mechanisms (may not be populated in v3.1)
  semantic_pivot?: SemanticPivot;
  semantic_expansion?: SemanticExpansion;
  chat_override?: ChatOverride;
}

/**
 * InterestItem - Single user interest with computed weight
 */
export interface InterestItem {
  topic: string;
  category: string;
  weight: number; // Computed effective weight (0.0-1.0)
  status: 'active' | 'blocked' | 'dormant';
  positive_signals: number;
  negative_signals: number;
}

/**
 * ExtractedInterest - Interest extracted/updated/deleted from conversation by LLM
 */
export interface ExtractedInterest {
  action?: 'create' | 'update' | 'delete'; // Default: 'create' for backward compat
  interest_id?: string | null; // UUID for update/delete
  topic: string;
  category: string;
  confidence: number; // LLM confidence (0.0-1.0)
}

/**
 * MatchingDecision - Action decision for an extracted interest
 */
export interface MatchingDecision {
  extracted_topic: string;
  action: 'consolidate' | 'create_new' | 'update' | 'delete';
  interest_id?: string | null;
  matched_interest: string | null;
  matched_category?: string;
  reason: string;
}

/**
 * InterestLLMMetadata - Token and model info from extraction LLM call
 */
export interface InterestLLMMetadata {
  model: string;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  total_tokens: number;
  temperature: number;
}

/**
 * InterestProfileMetrics - Interest detection for debug panel (LLM-based)
 * Shows interests detected in the current user message via LLM analysis.
 *
 * Note: Uses analyze_interests_for_debug() which performs LLM extraction.
 * Results are cached in Redis for reuse by background extraction.
 */
export interface InterestProfileMetrics {
  enabled: boolean; // Whether interest learning is enabled globally
  analyzed: boolean; // Whether analysis was actually performed
  // Interests extracted from current message (LLM analysis)
  extracted_interests: ExtractedInterest[];
  // Deduplication decisions for each extracted interest
  matching_decisions: MatchingDecision[];
  // Existing user interests (for comparison)
  existing_interests: InterestItem[];
  // LLM call metadata (tokens, model, etc.)
  llm_metadata: InterestLLMMetadata | null;
  // Why analysis was skipped (if analyzed=false)
  analysis_skipped_reason?: string;
  // Error if any
  error?: string;
}

/**
 * KnowledgeEnrichmentMetrics - Brave Search knowledge enrichment metrics
 * Shows detected keywords and injected context for LLM responses
 */
/**
 * Single result from Brave Search API
 */
export interface BraveSearchResult {
  title: string;
  description: string;
  url: string;
}

export interface KnowledgeEnrichmentMetrics {
  enabled: boolean; // Whether knowledge enrichment is enabled globally
  executed: boolean; // Whether enrichment was actually performed
  // Detected keywords from QueryAnalyzer
  encyclopedia_keywords: string[];
  is_news_query: boolean;
  // Enrichment results
  endpoint?: 'web' | 'news'; // Which Brave Search endpoint was used
  keyword_used?: string; // Combined keywords sent to API
  results_count?: number; // Number of results returned
  from_cache?: boolean; // Whether results came from Redis cache
  // Actual results for debugging (title, description, url)
  results?: BraveSearchResult[];
  // Formatted context injected into LLM prompt
  prompt_context?: string;
  // Skip/error info
  skip_reason?: string; // Why enrichment was skipped (no keywords, no connector, etc.)
  error?: string; // Error message if enrichment failed
}

/**
 * MemoryInjectionDebugItem - Single injected memory with score for debug panel tuning
 */
export interface MemoryInjectionDebugItem {
  content: string;
  category: string;
  score: number;
  emotional_weight: number;
}

/**
 * MemoryInjectionSettings - Settings used for memory injection
 */
export interface MemoryInjectionSettings {
  max_results: number;
  min_score: number;
  hybrid_enabled: boolean;
}

/**
 * MemoryInjectionMetrics - Debug details for injected memories
 * Used for tuning min_score and max_results parameters
 */
export interface MemoryInjectionMetrics {
  memory_count: number;
  emotional_state: string;
  settings: MemoryInjectionSettings;
  memories: MemoryInjectionDebugItem[];
}

/**
 * RAGInjectionChunk - Single injected RAG chunk with score for debug panel
 */
export interface RAGInjectionChunk {
  space: string;
  file: string;
  score: number;
}

/**
 * RAGInjectionMetrics - Debug details for injected RAG document chunks
 * Used for tuning retrieval parameters and verifying RAG behavior
 */
export interface RAGInjectionMetrics {
  spaces_searched: number;
  chunks_found: number;
  chunks_injected: number;
  chunks: RAGInjectionChunk[];
}

/**
 * JournalInjectionEntry - Single injected journal entry with score
 * Used for debug panel visualization of journal context injection
 */
export interface JournalInjectionEntry {
  theme: string;
  title: string; // First 25 chars
  full_title?: string; // Complete title
  content?: string; // Full entry content (for tooltip)
  score: number | null; // Similarity score (0.0-1.0), null for recent entries (temporal continuity)
  mood: string;
  char_count: number;
  source: string; // 'conversation' | 'consolidation' | 'manual'
  date: string; // YYYY-MM-DD
  injected: boolean; // Whether this entry was actually injected (budget constraint)
}

/**
 * JournalInjectionMetrics - Debug details for injected journal entries
 * Used for tuning context injection parameters and verifying journal behavior
 */
export interface JournalInjectionMetrics {
  entries_found: number; // Total entries matching semantic search
  entries_recent?: number; // Recent entries injected for temporal continuity
  entries_injected: number; // Entries actually injected (within budget)
  total_chars_injected: number; // Total characters injected into prompt
  max_chars_budget: number; // User's configured max chars
  max_results_setting: number; // User's configured max results
  entries: JournalInjectionEntry[];
}

/**
 * JournalExtractionEntry - Single journal action from background extraction
 * Shows what the assistant created/updated/deleted in its journals
 */
export interface JournalExtractionEntry {
  action: 'create' | 'update' | 'delete';
  theme: string | null;
  title: string | null; // First 30 chars
  full_title?: string | null; // Complete title
  content?: string | null; // Full entry content (for tooltip)
  mood: string | null;
  entry_id: string | null; // UUID for update/delete actions
}

/**
 * JournalExtractionMetrics - Debug details for background journal extraction
 * Shows what the assistant wrote in its journals after processing the conversation
 */
export interface JournalExtractionMetrics {
  actions_parsed: number; // Total actions parsed from LLM output
  actions_applied: number; // Actions successfully applied (create/update/delete)
  entries: JournalExtractionEntry[];
}

/**
 * ExtractedMemory - Memory extracted/updated/deleted from conversation by background LLM
 */
export interface ExtractedMemory {
  action?: 'create' | 'update' | 'delete'; // Default: 'create' for backward compat
  memory_id?: string | null; // UUID for update/delete
  content: string;
  category: string; // preference | personal | relationship | event | pattern | sensitivity
  emotional_weight: number; // -10 (trauma) to +10 (joy)
  importance: number; // 0.0-1.0
  trigger_topic?: string;
  stored: boolean; // Whether the action was successfully applied
}

/**
 * ExistingSimilarMemory - Existing memory found during deduplication search
 */
export interface ExistingSimilarMemory {
  content: string;
  category: string;
  score: number; // Semantic similarity score (0.0-1.0)
}

/**
 * MemoryDetectionLLMMetadata - Token and model info from memory extraction LLM call
 */
export interface MemoryDetectionLLMMetadata {
  model: string;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  total_tokens: number;
}

/**
 * MemoryDetectionMetrics - Memory detection/extraction for debug panel
 * Shows memories extracted from the current user message by background LLM analysis.
 *
 * Note: Data is captured from extract_memories_background() which runs as a
 * fire-and-forget task, awaited before SSE done emission.
 */
export interface MemoryDetectionMetrics {
  enabled: boolean; // Whether memory extraction is enabled globally
  // Memories extracted and stored from current message
  extracted_memories: ExtractedMemory[];
  // Existing similar memories found during deduplication
  existing_similar: ExistingSimilarMemory[];
  // LLM call metadata (tokens, model)
  llm_metadata: MemoryDetectionLLMMetadata | null;
  // Why extraction was skipped (if no memories extracted)
  skipped_reason?: string;
  // Error if any
  error?: string;
}

/**
 * DebugMetrics - Complete debug metrics from QueryIntelligence
 * Emitted via SSE when DEBUG=true in backend
 */
export interface DebugMetrics {
  intent_detection: IntentDetectionMetrics;
  domain_selection: DomainSelectionMetrics;
  routing_decision: RoutingDecisionMetrics;
  tool_selection?: ToolSelectionMetrics; // Optional: populated when tool_selection_result is available
  token_budget?: TokenBudget; // Optional: token context budget with zone indicators
  planner_intelligence?: PlannerIntelligence; // Optional: planner strategy and efficiency metrics
  execution_timeline?: ExecutionTimeline; // Optional: execution step timeline
  context_resolution: ContextResolutionMetrics;
  query_info: QueryInfoMetrics;
  // LLM Token Tracking (CORRECTION 2)
  llm_calls?: LLMCall[]; // Optional: detailed per-node LLM calls
  llm_summary?: LLMSummary; // Optional: aggregated LLM summary
  llm_pipeline?: LLMPipelineMetrics; // v3.3: chronological LLM call reconciliation
  // Google API Tracking
  google_api_calls?: GoogleApiCall[]; // Optional: detailed per-call Google API usage
  google_api_summary?: GoogleApiSummary; // Optional: aggregated Google API summary
  // Intelligent Mechanisms Tracking
  intelligent_mechanisms?: IntelligentMechanisms; // Optional: tracking of intelligent mechanisms
  // v3.1 Debug Panel Enrichments
  for_each_analysis?: ForEachAnalysis; // Optional: FOR_EACH bulk operation detection
  execution_waves?: ExecutionWavesInfo; // Optional: parallel execution wave analysis
  request_lifecycle?: RequestLifecycleMetrics; // Optional: pipeline node progression
  // Interest Learning System
  interest_profile?: InterestProfileMetrics; // Optional: user's learned interest profile
  // Knowledge Enrichment (Brave Search)
  knowledge_enrichment?: KnowledgeEnrichmentMetrics; // Optional: Brave Search knowledge enrichment
  // Memory Injection (debug tuning)
  memory_injection?: MemoryInjectionMetrics; // Optional: injected memories with scores for tuning
  // Memory Detection (long-term memory extraction)
  memory_detection?: MemoryDetectionMetrics; // Optional: memories extracted and stored from current message
  // RAG Injection (Knowledge Spaces)
  rag_injection?: RAGInjectionMetrics; // Optional: injected RAG chunks with scores
  // Journal Injection (Personal Journals - Response)
  journal_injection?: JournalInjectionMetrics; // Optional: injected journal entries with scores (response node)
  // Journal Injection (Personal Journals - Planner)
  journal_planner_injection?: JournalInjectionMetrics; // Optional: injected journal entries with scores (planner node)
  // Journal Extraction (Background creation)
  journal_extraction?: JournalExtractionMetrics; // Optional: journal entries created/updated/deleted
  // Skills activation
  skills?: SkillsMetrics; // Optional: skill activated for this turn
}

/**
 * DebugMetricsMetadata - SSE metadata for debug_metrics events
 * Alias type for DebugMetrics (no extension, just a semantic alias)
 */
export type DebugMetricsMetadata = DebugMetrics;

/**
 * SkillsMetrics - Skill activation details for debug panel
 */
export interface SkillsMetrics {
  activated: boolean;
  skill_name: string;
  activation_mode: 'bypass' | 'planner' | 'tool';
  is_deterministic: boolean;
  category?: string | null;
  priority?: number;
  has_scripts?: boolean;
  has_references?: boolean;
  scope?: 'admin' | 'user';
}
