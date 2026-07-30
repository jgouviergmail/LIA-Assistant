/**
 * Settings quick search — the index behind the "Search a setting" field.
 *
 * ## Why a second table
 *
 * `settings-sections.ts` answers "where does this token land". This module
 * answers "what does the reader call it", and the two are kept in lockstep by
 * the TYPE rather than by a test: `SETTINGS_SEARCH_META` is a
 * `Record<SettingsSectionToken, …>`, so adding a deep-link token without search
 * metadata does not compile. The reverse direction — a section the page renders
 * that neither table knows about — is held by
 * `__tests__/settings-sections-coverage.guard.test.ts`.
 *
 * ## What it can and cannot promise
 *
 * Twenty-two of the thirty sections always render. Eight do not, and only two
 * of those are decidable before the section mounts:
 *
 *   - `open-loops` reads an instance flag from `/config`;
 *   - `debug-panel` reads an admin-granted per-user flag, and the page only
 *     renders it in the NON-superuser layout;
 *   - the six others (`telephony-calls`, `security-auth`, `security-export`,
 *     `admin-mcp-servers`, `briefing-grid`, `heartbeat`) return null from their
 *     own data — a 404, an empty list, an instance without MFA, or simply a
 *     request still in flight.
 *
 * The six stay in the index on purpose. The settings page mounts one tab at a
 * time (Radix unmounts the inactive panel), so from the Preferences tab nothing
 * can observe what the Features tab would render; guessing would trade a
 * visible dead end for an invisible one. They are marked `runtime`, and the
 * caller tells the user plainly when the destination turns out not to exist.
 *
 * ## Matching
 *
 * Accent- and case-insensitive through `normalizeSearchText`, the single
 * matcher the whole search stack shares (FAQ, excerpts, highlighting, slash
 * commands). Chinese needs no special case: the haystack is matched as a
 * substring, which is what CJK without word boundaries requires anyway.
 */

import {
  SETTINGS_SECTIONS,
  type SettingsSectionTarget,
  type SettingsSectionToken,
} from '@/lib/settings-sections';
import { normalizeSearchText } from '@/lib/utils';

/**
 * Group heading a section sits under, as keyed in `settings.groups.*`.
 *
 * Only the groups of the two indexed tabs are listed; the administration
 * groups (`users_access`, `ai_connectors`, `content_extensions`, `system`) are
 * out of scope for phase 1.
 */
export type SettingsGroupKey =
  | 'personalization'
  | 'notifications_communication'
  | 'security'
  | 'voice_media'
  | 'connections_integrations'
  | 'identity_memory'
  | 'automation_tracking'
  | 'extensions_data';

/**
 * Why a section might not be on the page.
 *
 * A gate must mirror the guard the COMPONENT actually applies, never a flag it
 * ignores. `/config` also exposes `skills_enabled`, `channels_enabled`,
 * `journals_enabled`, `rag_spaces_enabled` and `heartbeat_enabled`, but
 * `SkillsSettings`, `ChannelSettings`, `JournalsSettings` and
 * `SpacesSettingsSection` never read them and render regardless — filtering on
 * those would hide sections that are right there on the page.
 */
export type SettingsSectionGate =
  | { kind: 'always' }
  | { kind: 'instanceFlag'; flag: 'openLoopsEnabled' | 'peersEnabled' }
  | { kind: 'userDebugPanel' }
  | { kind: 'runtime'; reason: string };

export interface SettingsSearchMeta {
  /** i18n key of the section title — the same one the section header renders. */
  titleKey: string;
  /** i18n key of the section description. */
  descriptionKey: string;
  /** i18n key of the extra search terms, a comma-separated list. */
  keywordsKey: string;
  group: SettingsGroupKey;
  gate: SettingsSectionGate;
}

/** Extra search terms, keyed by section token. */
const KEYWORDS_PREFIX = 'settings.search.keywords';

/**
 * Section token → what the reader would type to find it.
 *
 * Exhaustive by construction. Order is irrelevant here (the routing table owns
 * page order, which is what breaks score ties).
 */
export const SETTINGS_SEARCH_META: Readonly<Record<SettingsSectionToken, SettingsSearchMeta>> = {
  // ---- Preferences / Personalization
  language: {
    titleKey: 'settings.language.title',
    descriptionKey: 'settings.language.description',
    keywordsKey: `${KEYWORDS_PREFIX}.language`,
    group: 'personalization',
    gate: { kind: 'always' },
  },
  timezone: {
    titleKey: 'settings.timezone.title',
    descriptionKey: 'settings.timezone.description',
    keywordsKey: `${KEYWORDS_PREFIX}.timezone`,
    group: 'personalization',
    gate: { kind: 'always' },
  },
  theme: {
    titleKey: 'settings.theme.title',
    descriptionKey: 'settings.theme.description',
    keywordsKey: `${KEYWORDS_PREFIX}.theme`,
    group: 'personalization',
    gate: { kind: 'always' },
  },
  font: {
    titleKey: 'settings.font.title',
    descriptionKey: 'settings.font.description',
    keywordsKey: `${KEYWORDS_PREFIX}.font`,
    group: 'personalization',
    gate: { kind: 'always' },
  },
  'display-mode': {
    titleKey: 'settings.preferences.display_mode.title',
    descriptionKey: 'settings.preferences.display_mode.description',
    keywordsKey: `${KEYWORDS_PREFIX}.display-mode`,
    group: 'personalization',
    gate: { kind: 'always' },
  },
  'briefing-grid': {
    titleKey: 'settings.briefing_grid.title',
    descriptionKey: 'settings.briefing_grid.description',
    keywordsKey: `${KEYWORDS_PREFIX}.briefing-grid`,
    group: 'personalization',
    gate: { kind: 'runtime', reason: 'renders nothing until the briefing preferences load' },
  },
  'chat-shortcuts': {
    titleKey: 'settings.chat_shortcuts.title',
    descriptionKey: 'settings.chat_shortcuts.description',
    keywordsKey: `${KEYWORDS_PREFIX}.chat-shortcuts`,
    group: 'personalization',
    // `always`, unlike briefing-grid: the SECTION shell renders regardless —
    // only its body waits for the shortcuts to load.
    gate: { kind: 'always' },
  },
  'open-loops': {
    titleKey: 'settings.open_loops.title',
    descriptionKey: 'settings.open_loops.description',
    keywordsKey: `${KEYWORDS_PREFIX}.open-loops`,
    group: 'personalization',
    gate: { kind: 'instanceFlag', flag: 'openLoopsEnabled' },
  },

  // ---- Preferences / Notifications & Communication
  notifications: {
    titleKey: 'settings.notifications.title',
    descriptionKey: 'settings.notifications.description',
    keywordsKey: `${KEYWORDS_PREFIX}.notifications`,
    group: 'notifications_communication',
    gate: { kind: 'always' },
  },
  channels: {
    titleKey: 'settings.channels.title',
    descriptionKey: 'settings.channels.description',
    keywordsKey: `${KEYWORDS_PREFIX}.channels`,
    group: 'notifications_communication',
    gate: { kind: 'always' },
  },

  // ---- Preferences / Security
  'security-auth': {
    titleKey: 'settings.security.auth.title',
    descriptionKey: 'settings.security.auth.description',
    keywordsKey: `${KEYWORDS_PREFIX}.security-auth`,
    group: 'security',
    gate: { kind: 'runtime', reason: 'renders nothing on an instance without MFA enabled' },
  },
  'security-devices': {
    titleKey: 'settings.security.devices.title',
    descriptionKey: 'settings.security.devices.description',
    keywordsKey: `${KEYWORDS_PREFIX}.security-devices`,
    group: 'security',
    gate: { kind: 'always' },
  },
  'security-export': {
    titleKey: 'settings.security.export.title',
    descriptionKey: 'settings.security.export.description',
    keywordsKey: `${KEYWORDS_PREFIX}.security-export`,
    group: 'security',
    gate: { kind: 'runtime', reason: 'renders nothing when the export endpoint answers 404' },
  },

  // ---- Preferences / Voice & Media
  'voice-mode': {
    titleKey: 'settings.voice_mode.title',
    descriptionKey: 'settings.voice_mode.description',
    keywordsKey: `${KEYWORDS_PREFIX}.voice-mode`,
    group: 'voice_media',
    gate: { kind: 'always' },
  },
  'image-generation': {
    titleKey: 'settings.image_generation.title',
    descriptionKey: 'settings.image_generation.description',
    keywordsKey: `${KEYWORDS_PREFIX}.image-generation`,
    group: 'voice_media',
    gate: { kind: 'always' },
  },

  // ---- Preferences / Connections & Integrations
  connectors: {
    titleKey: 'settings.connectors.my_connectors',
    descriptionKey: 'settings.connectors.my_connectors_description',
    keywordsKey: `${KEYWORDS_PREFIX}.connectors`,
    group: 'connections_integrations',
    gate: { kind: 'always' },
  },
  'telephony-calls': {
    titleKey: 'settings.telephony.calls.title',
    descriptionKey: 'settings.telephony.calls.description',
    keywordsKey: `${KEYWORDS_PREFIX}.telephony-calls`,
    group: 'connections_integrations',
    gate: {
      kind: 'runtime',
      reason: 'renders nothing when telephony is off or no call was placed',
    },
  },
  'admin-mcp-servers': {
    titleKey: 'settings.admin_mcp.title',
    descriptionKey: 'settings.admin_mcp.description',
    keywordsKey: `${KEYWORDS_PREFIX}.admin-mcp-servers`,
    group: 'connections_integrations',
    gate: { kind: 'runtime', reason: 'renders nothing when the instance declares no MCP server' },
  },
  'mcp-servers': {
    titleKey: 'settings.mcp.title',
    descriptionKey: 'settings.mcp.description',
    keywordsKey: `${KEYWORDS_PREFIX}.mcp-servers`,
    group: 'connections_integrations',
    gate: { kind: 'always' },
  },
  // Sits in the "connections" group because that is where the page puts it —
  // the index reports the page as it is, it does not tidy it up.
  'debug-panel': {
    titleKey: 'settings.preferences.debug.title',
    descriptionKey: 'settings.preferences.debug.description',
    keywordsKey: `${KEYWORDS_PREFIX}.debug-panel`,
    group: 'connections_integrations',
    gate: { kind: 'userDebugPanel' },
  },

  // ---- Features / Identity & Memory
  personality: {
    titleKey: 'personality.settings.title',
    descriptionKey: 'personality.settings.description',
    keywordsKey: `${KEYWORDS_PREFIX}.personality`,
    group: 'identity_memory',
    gate: { kind: 'always' },
  },
  psyche: {
    titleKey: 'psyche.title',
    descriptionKey: 'psyche.description',
    keywordsKey: `${KEYWORDS_PREFIX}.psyche`,
    group: 'identity_memory',
    gate: { kind: 'always' },
  },
  memories: {
    titleKey: 'memories.settings.title',
    descriptionKey: 'memories.settings.description',
    keywordsKey: `${KEYWORDS_PREFIX}.memories`,
    group: 'identity_memory',
    gate: { kind: 'always' },
  },
  interests: {
    titleKey: 'interests.settings.title',
    descriptionKey: 'interests.settings.description',
    keywordsKey: `${KEYWORDS_PREFIX}.interests`,
    group: 'identity_memory',
    gate: { kind: 'always' },
  },
  'peer-connections': {
    titleKey: 'settings.peers.title',
    descriptionKey: 'settings.peers.description',
    keywordsKey: `${KEYWORDS_PREFIX}.peer-connections`,
    group: 'identity_memory',
    gate: { kind: 'instanceFlag', flag: 'peersEnabled' },
  },

  // ---- Features / Automation & Tracking
  heartbeat: {
    titleKey: 'heartbeat.settings.title',
    descriptionKey: 'heartbeat.settings.description',
    keywordsKey: `${KEYWORDS_PREFIX}.heartbeat`,
    group: 'automation_tracking',
    gate: { kind: 'runtime', reason: 'renders nothing until its own settings load' },
  },
  'scheduled-actions': {
    titleKey: 'scheduled_actions.settings.title',
    descriptionKey: 'scheduled_actions.settings.description',
    keywordsKey: `${KEYWORDS_PREFIX}.scheduled-actions`,
    group: 'automation_tracking',
    gate: { kind: 'always' },
  },
  journals: {
    titleKey: 'journals.title',
    descriptionKey: 'journals.description',
    keywordsKey: `${KEYWORDS_PREFIX}.journals`,
    group: 'automation_tracking',
    gate: { kind: 'always' },
  },
  'health-metrics': {
    titleKey: 'healthMetrics.title',
    descriptionKey: 'healthMetrics.description',
    keywordsKey: `${KEYWORDS_PREFIX}.health-metrics`,
    group: 'automation_tracking',
    gate: { kind: 'always' },
  },

  // ---- Features / Extensions & Data
  skills: {
    titleKey: 'settings.skills.title',
    descriptionKey: 'settings.skills.description',
    keywordsKey: `${KEYWORDS_PREFIX}.skills`,
    group: 'extensions_data',
    gate: { kind: 'always' },
  },
  'rag-spaces': {
    titleKey: 'settings.rag_spaces.title',
    descriptionKey: 'settings.rag_spaces.description',
    keywordsKey: `${KEYWORDS_PREFIX}.rag-spaces`,
    group: 'extensions_data',
    gate: { kind: 'always' },
  },
  'user-consumption-export': {
    titleKey: 'settings.user.export.title',
    descriptionKey: 'settings.user.export.description',
    keywordsKey: `${KEYWORDS_PREFIX}.user-consumption-export`,
    group: 'extensions_data',
    gate: { kind: 'always' },
  },
};

/**
 * What the page knows about this user and this instance.
 *
 * Flattened on purpose: every field is a resolved boolean, so this module never
 * has to know which endpoint it came from, and a test can state a situation
 * without mocking a hook. All three default to the RESTRICTIVE value while
 * their request is in flight, which mirrors the components — and the index
 * rebuilds by itself once they land.
 */
export interface SettingsSearchAvailability {
  isSuperuser: boolean;
  /** `/config` → `features.open_loops_enabled`. */
  openLoopsEnabled: boolean;
  /** `/config` → `features.peers_enabled` (peers program). */
  peersEnabled: boolean;
  /** `useDebugPanelEnabled()` → `userAccessAvailable`. */
  debugUserAccess: boolean;
}

/** One indexed section, with its translated text pre-normalized for matching. */
export interface SettingsSearchEntry {
  token: SettingsSectionToken;
  target: SettingsSectionTarget;
  group: SettingsGroupKey;
  /** Translated section title, as displayed. */
  title: string;
  /** Translated section description, as displayed. */
  description: string;
  /** Normalized title, matched first. */
  normalizedTitle: string;
  /** Normalized keywords and group label, matched second. */
  normalizedKeywords: string;
  /** Normalized description, matched last. */
  normalizedDescription: string;
}

/** A hit, richest match first. */
export interface SettingsSearchResult extends SettingsSearchEntry {
  /**
   * Where the query was found. `title` lets the caller skip the description
   * line, which would otherwise repeat what the reader already sees.
   */
  matchedIn: 'title' | 'keywords' | 'description';
  /** Higher is a better match; see {@link MATCH_SCORE}. */
  score: number;
}

/**
 * Match tiers.
 *
 * A title that STARTS with the query outranks one that merely contains it:
 * typing "not" should put "Notifications push" above a section whose
 * description happens to mention a notification.
 */
const MATCH_SCORE = {
  titlePrefix: 5,
  title: 4,
  keywords: 3,
  description: 2,
  /** Every query word found somewhere, but not as one phrase. */
  allWords: 1,
} as const;

/** Minimal shape of the i18n `t` — keeps this module free of react-i18next. */
export type SettingsTranslate = (key: string) => string;

/**
 * Whether a section can be on the page at all for this user and instance.
 *
 * `runtime` gates answer true: they are undecidable from here, and dropping
 * them would turn "the section is empty today" into "the setting does not
 * exist", which is the worse of the two lies.
 *
 * @param gate - The section's declared gate.
 * @param availability - Resolved flags for this user and instance.
 * @returns False only when the section is provably absent.
 */
export function isSectionAvailable(
  gate: SettingsSectionGate,
  availability: SettingsSearchAvailability
): boolean {
  switch (gate.kind) {
    case 'instanceFlag':
      return availability[gate.flag];
    case 'userDebugPanel':
      // The page renders `UserDebugSettings` in the non-superuser layout only;
      // a superuser gets the richer admin debug section in another tab.
      return availability.debugUserAccess && !availability.isSuperuser;
    case 'runtime':
    case 'always':
      return true;
  }
}

/**
 * Build the searchable index in the active language.
 *
 * Called from a `useMemo` keyed on `t` and the availability flags: react-i18next
 * hands back a new `t` when the language or the resources change, so a language
 * switch rebuilds the index rather than leaving it in the previous language.
 *
 * @param t - Translator for the active language.
 * @param availability - Resolved flags for this user and instance.
 * @returns Available sections, in page order.
 */
export function buildSettingsSearchIndex(
  t: SettingsTranslate,
  availability: SettingsSearchAvailability
): SettingsSearchEntry[] {
  const entries: SettingsSearchEntry[] = [];

  // `SETTINGS_SECTIONS` is iterated, not `SETTINGS_SEARCH_META`: page order is
  // declared there and it is what breaks score ties.
  for (const [token, target] of Object.entries(SETTINGS_SECTIONS) as Array<
    [SettingsSectionToken, SettingsSectionTarget]
  >) {
    const meta = SETTINGS_SEARCH_META[token];
    if (!isSectionAvailable(meta.gate, availability)) continue;

    const title = t(meta.titleKey);
    const description = t(meta.descriptionKey);
    // The group heading joins the keyword tier: "Security" is the only word
    // shared by the three security sections, and none of their titles or
    // descriptions contains it.
    const keywords = `${t(meta.keywordsKey)}, ${t(`settings.groups.${meta.group}`)}`;

    entries.push({
      token,
      target,
      group: meta.group,
      title,
      description,
      normalizedTitle: normalizeSearchText(title),
      normalizedKeywords: normalizeSearchText(keywords),
      normalizedDescription: normalizeSearchText(description),
    });
  }

  return entries;
}

/**
 * Score one entry against an already-normalized query.
 *
 * @returns The tier and its score, or null when nothing matched.
 */
function scoreEntry(
  entry: SettingsSearchEntry,
  normalizedQuery: string,
  words: string[]
): Pick<SettingsSearchResult, 'matchedIn' | 'score'> | null {
  if (entry.normalizedTitle.startsWith(normalizedQuery)) {
    return { matchedIn: 'title', score: MATCH_SCORE.titlePrefix };
  }
  if (entry.normalizedTitle.includes(normalizedQuery)) {
    return { matchedIn: 'title', score: MATCH_SCORE.title };
  }
  if (entry.normalizedKeywords.includes(normalizedQuery)) {
    return { matchedIn: 'keywords', score: MATCH_SCORE.keywords };
  }
  if (entry.normalizedDescription.includes(normalizedQuery)) {
    return { matchedIn: 'description', score: MATCH_SCORE.description };
  }
  // Last resort: the words are all there but not in that order. "notification
  // push" must find "Notifications push"; requiring the exact phrase would make
  // word order a hidden syntax rule.
  if (words.length > 1) {
    const haystack = `${entry.normalizedTitle} ${entry.normalizedKeywords} ${entry.normalizedDescription}`;
    if (words.every(word => haystack.includes(word))) {
      return { matchedIn: 'description', score: MATCH_SCORE.allWords };
    }
  }
  return null;
}

/**
 * Sections matching a raw query, best match first.
 *
 * Never truncated: a silently capped list reads as "nothing else matches". The
 * caller scrolls its listbox instead.
 *
 * @param index - Output of {@link buildSettingsSearchIndex}.
 * @param query - Raw user input; blank input yields no results.
 * @returns Matches sorted by score, ties broken by page order.
 */
export function matchSettingsSections(
  index: readonly SettingsSearchEntry[],
  query: string
): SettingsSearchResult[] {
  const normalizedQuery = normalizeSearchText(query.trim());
  if (!normalizedQuery) return [];

  const words = normalizedQuery.split(/\s+/).filter(Boolean);
  const results: SettingsSearchResult[] = [];

  for (const entry of index) {
    const hit = scoreEntry(entry, normalizedQuery, words);
    if (hit) results.push({ ...entry, ...hit });
  }

  // `sort` is stable in every engine the app targets, so equal scores keep the
  // page order `index` arrived in.
  return results.sort((left, right) => right.score - left.score);
}
