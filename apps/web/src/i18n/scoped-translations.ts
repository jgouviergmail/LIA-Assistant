/**
 * Translation subtrees the browser receives only where a client component
 * reads them.
 *
 * The root layout hands its client `TranslationsProvider` the language's
 * catalogue, and React serialises those props into EVERY page's payload. Whole,
 * that is 2.2 MB of French on a landing page that reads a fraction of it
 * (measured 2026-10-28: 3.36 MB of HTML, 2.58 MB of it RSC payload). Four
 * subtrees weigh 63 % of the catalogue and are read in the browser by two pages
 * at most:
 *
 * - `faq.sections` — the public FAQ and the dashboard FAQ;
 * - `faq.changelog`, `faq.intro` — the dashboard FAQ (the landing band and the
 *   changelog page render the releases on the SERVER);
 * - `blog` — no client component (the blog pages and the landing's preview
 *   resolve every string on the server).
 *
 * So the root layout ships the catalogue WITHOUT them
 * (`omitTranslations(..., ROUTE_SCOPED_TRANSLATIONS)`), and a route whose client
 * components read one wraps them in `<ScopedTranslations scopes={[...]}>`, which
 * adds those subtrees back under that route only. Server components are
 * unaffected: `initI18next` keeps the whole catalogue.
 *
 * The application catalogues also stay out of public pages. The dashboard's
 * server layout supplies them around its client shell; the public demo and
 * animated examples receive only the groups their reused components read.
 * The language selector's small `settings.language` subtree stays shared.
 * `__tests__/scoped-translations.guard.test.ts` walks the import graph and
 * checks each reader against its page and inherited layout scopes.
 */

/** Settings used by the application and the public /more settings examples. */
const SETTINGS_TRANSLATION_SCOPES = [
  'settings.application_tools',
  'settings.avatar',
  'settings.title',
  'settings.subtitle',
  'settings.tabs',
  'settings.groups',
  'settings.theme',
  'settings.font',
  'settings.font_size',
  'settings.timezone',
  'settings.voice_language_filter',
  'settings.voice_mode',
  'settings.voice_sample',
  'settings.image_generation',
  'settings.admin_mcp',
  'settings.mcp',
  'settings.sandbox_egress',
  'settings.preferences',
  'settings.usage_preferences',
  'settings.interests',
  'settings.peers',
  'settings.notifications',
  'settings.location',
  'settings.profile',
  'settings.connectors',
  'settings.user',
  'settings.admin',
  'settings.skills',
  'settings.channels',
  'settings.rag_spaces',
  'settings.portrait_shortcut',
  'settings.chat_shortcuts',
  'settings.my_shortcuts',
  'settings.briefing_grid',
  'settings.open_loops',
  'settings.habits',
  'settings.security',
  'settings.telephony',
  'settings.shell',
  'settings.search',
  'settings.haptics',
  'settings.plugins',
  'settings.eyes_style',
  'settings.meetings',
  'settings.generated_assets',
  'settings.bookmarks',
  'settings.live_mode',
  'settings.capability_share',
] as const;

/** Personal settings also read by /more's interactive examples. */
const PERSONAL_TRANSLATION_SCOPES = [
  'personality',
  'memories',
  'interests',
  'heartbeat',
  'scheduled_actions',
  'journals',
  'usage_limits',
  'healthMetrics',
  'psyche',
  'reminders',
  'radio',
  'sms',
  'discussions',
] as const;

/** The dashboard shell and its descendants share this application catalogue. */
export const DASHBOARD_TRANSLATION_SCOPES = [
  ...SETTINGS_TRANSLATION_SCOPES,
  ...PERSONAL_TRANSLATION_SCOPES,
  'broadcast',
  'executionMode',
  'voice',
  'tokens_display',
  'activity',
  'dashboard',
  'relations',
  'spaces',
  'navigation',
  'validation',
  'hitl',
  'execution',
  'companion',
  'shortcuts_dock',
  'lars',
  'draft',
  'notifications',
  'designSystem',
  'onboarding',
  'browser',
  'conversations',
  'notifications_hub',
  'provenance',
  'documents',
  'meetings',
  'effects',
  'registers',
  'recurrence',
  'workboard',
  'moments',
  'live',
  'email_share',
] as const;

/** The /more scenes reuse personal/settings labels but no dashboard shell. */
export const MORE_TRANSLATION_SCOPES = [
  ...SETTINGS_TRANSLATION_SCOPES,
  ...PERSONAL_TRANSLATION_SCOPES,
  'more',
] as const;

/** Dotted paths of the subtrees the root layout leaves out. */
export const ROUTE_SCOPED_TRANSLATIONS = [
  'faq.sections',
  'faq.changelog',
  'faq.intro',
  'blog',
  ...DASHBOARD_TRANSLATION_SCOPES,
  'more',
  'showroom',
] as const;

export type RouteScopedTranslation = (typeof ROUTE_SCOPED_TRANSLATIONS)[number];

/**
 * What a route asks for: a whole route-scoped subtree, or only some of its
 * children — the public FAQ reads its public sections alone (`PUBLIC_FAQ_SECTIONS`),
 * about a quarter of the subtree's weight when this was written.
 */
export type ScopedTranslationRequest =
  | RouteScopedTranslation
  | { readonly root: RouteScopedTranslation; readonly keys: readonly string[] };

/**
 * The dotted paths a route's requests stand for.
 *
 * @param requests - The route's requests.
 * @returns One path per whole subtree or per requested child.
 */
export function scopedTranslationPaths(
  requests: readonly ScopedTranslationRequest[]
): readonly string[] {
  return requests.flatMap(request =>
    typeof request === 'string' ? [request] : request.keys.map(key => `${request.root}.${key}`)
  );
}

/** One language's catalogue, or a part of it. */
export type TranslationTree = Readonly<Record<string, unknown>>;

/**
 * Whether a value is a subtree rather than a string, a number or a list.
 *
 * @param value - Any catalogue value.
 * @returns True for a plain object.
 */
export function isTranslationTree(value: unknown): value is TranslationTree {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function omitPath(tree: TranslationTree, [head, ...rest]: readonly string[]): TranslationTree {
  if (!Object.hasOwn(tree, head)) return tree;
  if (rest.length === 0) {
    return Object.fromEntries(Object.entries(tree).filter(([key]) => key !== head));
  }
  const child = tree[head];
  if (!isTranslationTree(child)) return tree;
  const kept = omitPath(child, rest);
  return kept === child ? tree : { ...tree, [head]: kept };
}

function pickPath(tree: TranslationTree, [head, ...rest]: readonly string[]): TranslationTree {
  if (!Object.hasOwn(tree, head)) return {};
  const child = tree[head];
  if (rest.length === 0) return { [head]: child };
  return isTranslationTree(child) ? { [head]: pickPath(child, rest) } : {};
}

/**
 * The catalogue without some subtrees. Branches the paths do not touch are
 * shared, never copied; nothing is mutated.
 *
 * @param tree - A language's catalogue.
 * @param paths - Dotted paths of the subtrees to leave out.
 * @returns The tree without them — `tree` itself when it holds none of them.
 */
export function omitTranslations(tree: TranslationTree, paths: readonly string[]): TranslationTree {
  return paths.reduce((kept, path) => omitPath(kept, path.split('.')), tree);
}

/**
 * Only some subtrees of the catalogue, at their place in it.
 *
 * @param tree - A language's catalogue.
 * @param paths - Dotted paths of the subtrees to keep.
 * @returns A new tree holding those subtrees alone.
 */
export function pickTranslations(tree: TranslationTree, paths: readonly string[]): TranslationTree {
  return paths.reduce<TranslationTree>(
    (picked, path) => mergeTranslations(picked, pickPath(tree, path.split('.'))),
    {}
  );
}

/**
 * Two trees as one: subtrees are merged key by key, any other value of
 * `extra` wins. Nothing is mutated.
 *
 * @param base - The tree already held.
 * @param extra - The subtrees to add.
 * @returns A new tree.
 */
export function mergeTranslations(base: TranslationTree, extra: TranslationTree): TranslationTree {
  const merged: Record<string, unknown> = { ...base };
  for (const [key, value] of Object.entries(extra)) {
    const current = merged[key];
    merged[key] =
      isTranslationTree(current) && isTranslationTree(value)
        ? mergeTranslations(current, value)
        : value;
  }
  return merged;
}
