/**
 * Blog article metadata and category definitions.
 *
 * Article content (title, excerpt, body) lives in the translation JSON files
 * under the `blog.articles.<slug>` namespace.
 */

export type BlogCategory = 'architecture' | 'integrations' | 'features' | 'security' | 'technical';

export interface BlogArticle {
  slug: string;
  category: BlogCategory;
  /** Lucide icon name for the article card */
  icon: string;
  /** ISO date string (publication date) */
  date: string;
  /** Estimated reading time in minutes */
  readTime: number;
  /** SEO keywords / tags */
  tags: string[];
}

/**
 * All blog categories in display order.
 * Labels are translation keys: `blog.categories.<id>`.
 */
export const BLOG_CATEGORIES: { id: BlogCategory; icon: string }[] = [
  { id: 'architecture', icon: 'Cpu' },
  { id: 'integrations', icon: 'Plug' },
  { id: 'features', icon: 'Sparkles' },
  { id: 'security', icon: 'Shield' },
  { id: 'technical', icon: 'Code' },
];

/**
 * All blog articles sorted by date (newest first).
 * The slug maps to translation keys: `blog.articles.<slug>.title`, `.excerpt`, `.body`.
 */
export const BLOG_ARTICLES: BlogArticle[] = [
  // --- Architecture ---
  {
    slug: 'react-execution-mode',
    category: 'architecture',
    icon: 'Repeat',
    date: '2026-04-08',
    readTime: 5,
    tags: ['react', 'pipeline', 'execution-mode', 'langgraph', 'iteration', 'agent-loop'],
  },
  {
    slug: 'multi-agent-orchestration',
    category: 'architecture',
    icon: 'Network',
    date: '2026-03-15',
    readTime: 6,
    tags: ['langgraph', 'multi-agent', 'orchestration', 'routing', 'ai-architecture'],
  },
  {
    slug: 'execution-plans',
    category: 'architecture',
    icon: 'ListChecks',
    date: '2026-03-12',
    readTime: 5,
    tags: ['planner', 'execution-plan', 'task-orchestration', 'parallel-execution'],
  },
  {
    slug: 'human-in-the-loop',
    category: 'architecture',
    icon: 'ShieldCheck',
    date: '2026-03-10',
    readTime: 5,
    tags: ['hitl', 'approval', 'human-validation', 'safety', 'trust'],
  },
  {
    slug: 'llm-providers',
    category: 'architecture',
    icon: 'Brain',
    date: '2026-03-08',
    readTime: 4,
    tags: ['openai', 'anthropic', 'google', 'deepseek', 'ollama', 'multi-provider'],
  },

  // --- Integrations ---
  {
    slug: 'mcp-react-agent',
    category: 'integrations',
    icon: 'Bot',
    date: '2026-04-05',
    readTime: 5,
    tags: ['mcp', 'react-agent', 'iterative', 'sub-agent', 'tool-server', 'extensibility'],
  },
  {
    slug: 'google-workspace',
    category: 'integrations',
    icon: 'Mail',
    date: '2026-03-14',
    readTime: 5,
    tags: ['google', 'gmail', 'calendar', 'drive', 'contacts', 'oauth'],
  },
  {
    slug: 'apple-microsoft',
    category: 'integrations',
    icon: 'Cloud',
    date: '2026-03-11',
    readTime: 4,
    tags: ['apple', 'icloud', 'microsoft', 'outlook', 'office-365'],
  },
  {
    slug: 'mcp-protocol',
    category: 'integrations',
    icon: 'Puzzle',
    date: '2026-03-06',
    readTime: 5,
    tags: ['mcp', 'model-context-protocol', 'extensibility', 'tools', 'api'],
  },
  {
    slug: 'skills-system',
    category: 'integrations',
    icon: 'Wand2',
    date: '2026-03-04',
    readTime: 4,
    tags: ['skills', 'skill-generator', 'customization', 'agentskills'],
  },

  // --- Features ---
  {
    slug: 'psyche-engine',
    category: 'features',
    icon: 'Heart',
    date: '2026-04-07',
    readTime: 5,
    tags: ['psyche', 'emotions', 'personality', 'emotional-intelligence', 'pad-model', 'big-five'],
  },
  {
    slug: 'progressive-steps',
    category: 'features',
    icon: 'ListOrdered',
    date: '2026-04-10',
    readTime: 4,
    tags: ['execution-steps', 'real-time', 'progressive-display', 'sse', 'ux', 'transparency'],
  },
  {
    slug: 'voice-mode',
    category: 'features',
    icon: 'Mic',
    date: '2026-03-13',
    readTime: 5,
    tags: ['voice', 'speech-to-text', 'tts', 'wake-word', 'hands-free'],
  },
  {
    slug: 'knowledge-spaces',
    category: 'features',
    icon: 'BookOpen',
    date: '2026-03-09',
    readTime: 5,
    tags: ['rag', 'documents', 'hybrid-search', 'embeddings', 'knowledge-base'],
  },
  {
    slug: 'personal-journals',
    category: 'features',
    icon: 'NotebookPen',
    date: '2026-03-18',
    readTime: 5,
    tags: ['journals', 'introspection', 'personality', 'memory', 'carnets-de-bord'],
  },
  {
    slug: 'proactive-notifications',
    category: 'features',
    icon: 'Bell',
    date: '2026-03-07',
    readTime: 4,
    tags: ['heartbeat', 'notifications', 'proactive', 'context-aware'],
  },
  {
    slug: 'reminders-scheduling',
    category: 'features',
    icon: 'Clock',
    date: '2026-03-03',
    readTime: 4,
    tags: ['reminders', 'scheduled-actions', 'automation', 'cron'],
  },
  {
    slug: 'sub-agents',
    category: 'features',
    icon: 'Users',
    date: '2026-03-01',
    readTime: 4,
    tags: ['sub-agents', 'delegation', 'parallel', 'specialists'],
  },

  // --- Security ---
  {
    slug: 'account-lifecycle',
    category: 'security',
    icon: 'UserCog',
    date: '2026-04-03',
    readTime: 5,
    tags: ['account', 'lifecycle', 'gdpr', 'soft-delete', 'erasure', 'data-retention'],
  },
  {
    slug: 'hallucination-defense',
    category: 'security',
    icon: 'ShieldAlert',
    date: '2026-04-06',
    readTime: 4,
    tags: ['hallucination', 'defense', 'parameter-stripping', 'hitl', 'robustness', 'planner'],
  },
  {
    slug: 'security-architecture',
    category: 'security',
    icon: 'Lock',
    date: '2026-03-16',
    readTime: 5,
    tags: ['security', 'defense-in-depth', 'rate-limiting', 'encryption'],
  },
  {
    slug: 'privacy-by-design',
    category: 'security',
    icon: 'Eye',
    date: '2026-03-05',
    readTime: 4,
    tags: ['privacy', 'gdpr', 'data-protection', 'pii', 'encryption'],
  },

  // --- Technical ---
  {
    slug: 'embedding-calibration',
    category: 'technical',
    icon: 'SlidersHorizontal',
    date: '2026-04-04',
    readTime: 5,
    tags: ['embeddings', 'similarity', 'calibration', 'gemini', 'thresholds', 'f1-score'],
  },
  {
    slug: 'llm-config-governance',
    category: 'technical',
    icon: 'Settings',
    date: '2026-04-09',
    readTime: 4,
    tags: ['llm-config', 'admin-ui', 'governance', 'db-overrides', 'multi-provider', 'defaults'],
  },
  {
    slug: 'observability',
    category: 'technical',
    icon: 'Activity',
    date: '2026-03-17',
    readTime: 5,
    tags: ['prometheus', 'grafana', 'langfuse', 'metrics', 'observability', 'devops', 'claude-cli'],
  },
  {
    slug: 'prompt-engineering',
    category: 'technical',
    icon: 'FileText',
    date: '2026-03-02',
    readTime: 4,
    tags: ['prompts', 'versioning', 'prompt-engineering', 'llm'],
  },
  {
    slug: 'smart-services',
    category: 'technical',
    icon: 'Zap',
    date: '2026-02-28',
    readTime: 4,
    tags: ['optimization', 'caching', 'pattern-learning', 'token-reduction'],
  },
  {
    slug: 'multilingual',
    category: 'technical',
    icon: 'Globe',
    date: '2026-02-25',
    readTime: 4,
    tags: ['i18n', 'multilingual', 'localization', '6-languages'],
  },
];

/**
 * Get articles filtered by category.
 */
export function getArticlesByCategory(category: BlogCategory): BlogArticle[] {
  return BLOG_ARTICLES.filter((a) => a.category === category);
}

/**
 * Find an article by its slug.
 */
export function getArticleBySlug(slug: string): BlogArticle | undefined {
  return BLOG_ARTICLES.find((a) => a.slug === slug);
}

/**
 * Get adjacent articles for navigation (prev/next).
 */
export function getAdjacentArticles(slug: string): {
  prev: BlogArticle | undefined;
  next: BlogArticle | undefined;
} {
  const idx = BLOG_ARTICLES.findIndex((a) => a.slug === slug);
  return {
    prev: idx > 0 ? BLOG_ARTICLES[idx - 1] : undefined,
    next: idx < BLOG_ARTICLES.length - 1 ? BLOG_ARTICLES[idx + 1] : undefined,
  };
}
