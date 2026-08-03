/**
 * Settings quick search — the index, its gates and its matching.
 *
 * Three classes of assertion, deliberately separated:
 *
 *  1. the METADATA describes the page it claims to describe — every key
 *     resolves in the six locales, every key is the one the component really
 *     calls, every group is the group the page puts the section in. A table
 *     that drifts is a search that lies about where things are;
 *  2. the GATES mirror each component's own guard. Over-filtering is the
 *     failure mode nobody notices: the section is right there and the search
 *     says it does not exist;
 *  3. the MATCHING, checked twice — once against a stub translator, so the
 *     ranking rules are pinned independently of any wording, and once against
 *     the REAL six dictionaries, so the recall claims ("mot de passe finds
 *     Strong authentication") are measured rather than asserted.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, it, expect } from 'vitest';

import deDict from '../../../locales/de/translation.json';
import enDict from '../../../locales/en/translation.json';
import esDict from '../../../locales/es/translation.json';
import frDict from '../../../locales/fr/translation.json';
import itDict from '../../../locales/it/translation.json';
import zhDict from '../../../locales/zh/translation.json';
import {
  buildSettingsSearchIndex,
  isSectionAvailable,
  matchSettingsSections,
  SETTINGS_SEARCH_META,
  type SettingsSearchAvailability,
  type SettingsTranslate,
} from '../settings-search';
import { SETTINGS_SECTIONS, type SettingsSectionToken } from '../settings-sections';
import {
  componentGroupsIn,
  exportedComponentOf,
  settingsPageBlocks,
  SRC,
} from './helpers/settings-page-source';

const LOCALES = { en: enDict, fr: frDict, de: deDict, es: esDict, it: itDict, zh: zhDict } as const;
type LocaleCode = keyof typeof LOCALES;

const TOKENS = Object.keys(SETTINGS_SECTIONS) as SettingsSectionToken[];

/** Everything present: the baseline the gate tests deviate from one field at a time. */
const ALL_AVAILABLE: SettingsSearchAvailability = {
  isSuperuser: false,
  openLoopsEnabled: true,
  peersEnabled: true,
  debugUserAccess: true,
};

function resolve(dictionary: unknown, path: string): unknown {
  return path.split('.').reduce<unknown>((node, part) => {
    if (node && typeof node === 'object' && part in (node as Record<string, unknown>)) {
      return (node as Record<string, unknown>)[part];
    }
    return undefined;
  }, dictionary);
}

/** A translator backed by a real locale file — missing keys surface as the key. */
function translatorFor(locale: LocaleCode): SettingsTranslate {
  return key => {
    const value = resolve(LOCALES[locale], key);
    return typeof value === 'string' ? value : key;
  };
}

/** A translator that echoes the key, so tests can pin ranking without wording. */
const echo: SettingsTranslate = key => key;

describe('SETTINGS_SEARCH_META — describes the page it claims to describe', () => {
  it('covers every deep-link token exactly once', () => {
    // The type already forbids a missing entry; this catches the reverse, an
    // entry left behind by a token that was removed.
    expect(Object.keys(SETTINGS_SEARCH_META).sort()).toEqual([...TOKENS].sort());
    // 30 at ADR-172, +1 chat-shortcuts (UX Actions program, SLASH admin lot),
    // +1 peer-connections (peers program, Lot 2), +1 haptics (its own sensory
    // control — `prefers-reduced-motion` is about animation, not touch).
    expect(TOKENS).toHaveLength(33);
  });

  it.each(Object.keys(LOCALES) as LocaleCode[])(
    'resolves every title, description and keyword list in %s',
    locale => {
      const missing: string[] = [];
      for (const token of TOKENS) {
        const meta = SETTINGS_SEARCH_META[token];
        for (const key of [meta.titleKey, meta.descriptionKey, meta.keywordsKey]) {
          const value = resolve(LOCALES[locale], key);
          if (typeof value !== 'string' || !value.trim()) missing.push(`${token} → ${key}`);
        }
        const groupLabel = resolve(LOCALES[locale], `settings.groups.${meta.group}`);
        if (typeof groupLabel !== 'string' || !groupLabel.trim()) {
          missing.push(`${token} → settings.groups.${meta.group}`);
        }
      }
      // A missing key does not crash i18next: it prints the key. Search results
      // would then read "settings.theme.title" — visible, and green everywhere
      // else. Same failure mode `i18n-key-placement.guard.test.ts` exists for,
      // covered here by the table instead of a hand-maintained list.
      expect(missing, `${locale}: unresolved i18n keys\n  ${missing.join('\n  ')}`).toEqual([]);
    }
  );

  it('never gives two sections the same title in the same tab', () => {
    // Two identical rows in one tab are indistinguishable. Across tabs they are
    // fine — the row shows the tab — which is exactly the case of "Debug Panel"
    // (Preferences) versus the admin debug section (Administration).
    const seen = new Map<string, string>();
    const clashes: string[] = [];
    for (const token of TOKENS) {
      const meta = SETTINGS_SEARCH_META[token];
      const label = `${SETTINGS_SECTIONS[token].tab}/${translatorFor('en')(meta.titleKey)}`;
      const previous = seen.get(label);
      if (previous) clashes.push(`${previous} and ${token} both render "${label}"`);
      seen.set(label, token);
    }
    expect(clashes).toEqual([]);
  });

  /**
   * The i18n keys must be the ones the COMPONENT calls.
   *
   * Both sides exist independently: the meta table for the search row, the
   * component for the section header. If they drift, the search names a section
   * something the page never shows — no crash, no failing key, just a result
   * the user cannot reconcile with what they land on.
   */
  const INTERPOLATED_KEY_TOKENS: ReadonlySet<string> = new Set(['user-consumption-export']);

  it.each(TOKENS)('%s uses the same i18n keys as its component', token => {
    const meta = SETTINGS_SEARCH_META[token];
    // Prettier wraps a long `t('key', 'fallback')` call onto three lines, so
    // the key stops following `t(` in the raw text. Collapsing the whitespace
    // right after `t(` keeps the assertion strict about the CALL — a key merely
    // mentioned in a comment still does not count — without being a formatting
    // assertion in disguise.
    const source = readFileSync(join(SRC, SETTINGS_SECTIONS[token].declaredIn), 'utf8').replace(
      /\bt\(\s+/g,
      't('
    );

    for (const key of [meta.titleKey, meta.descriptionKey]) {
      if (INTERPOLATED_KEY_TOKENS.has(token)) {
        // `ConsumptionExportSection` builds its keys from a `mode`-indexed
        // prefix (`t(\`${i18n}.title\`)`), so only the prefix is a literal.
        // Enumerated, like the sibling guard's computed-value hatch: a blanket
        // "prefix is enough" rule would relax the check for every section.
        const prefix = key.slice(0, key.lastIndexOf('.'));
        expect(
          source.includes(`'${prefix}'`),
          `${token}: ${SETTINGS_SECTIONS[token].declaredIn} never mentions the prefix '${prefix}'`
        ).toBe(true);
        continue;
      }
      expect(
        source.includes(`t('${key}'`),
        `${token}: ${SETTINGS_SECTIONS[token].declaredIn} does not call t('${key}')`
      ).toBe(true);
    }
  });

  it('places every section in the group the page puts it in', () => {
    // Derived from the page, never declared twice: the group is what the reader
    // sees above the section, so a section moved under another heading must
    // move in the search rows too.
    // `string | null`: a component rendered before the first heading (the
    // `<Accordion>` opening each panel) legitimately has no group. A SECTION
    // with a null group would surface below as a mismatch, which is the point.
    const pageGroups = new Map<string, string | null>();
    for (const block of settingsPageBlocks()) {
      for (const { component, group } of componentGroupsIn(block.body)) {
        pageGroups.set(component, group);
      }
    }

    const drift: string[] = [];
    for (const token of TOKENS) {
      const component = exportedComponentOf(SETTINGS_SECTIONS[token].declaredIn);
      const onPage = pageGroups.get(component);
      const declared = SETTINGS_SEARCH_META[token].group;
      if (onPage !== declared) {
        drift.push(`${token}: declared "${declared}", page renders it under "${onPage}"`);
      }
    }
    expect(drift, drift.join('\n  ')).toEqual([]);
  });

  it('marks as runtime exactly the sections that can vanish', () => {
    // Pinned so that turning a gate into `runtime` — which silently disables
    // filtering for that section — is a deliberate, reviewed edit.
    const runtime = TOKENS.filter(token => SETTINGS_SEARCH_META[token].gate.kind === 'runtime');
    expect(runtime.sort()).toEqual(
      [
        'admin-mcp-servers',
        'briefing-grid',
        'heartbeat',
        'security-auth',
        'security-export',
        'telephony-calls',
      ].sort()
    );
  });

  it('gives every runtime gate a written reason', () => {
    for (const token of TOKENS) {
      const gate = SETTINGS_SEARCH_META[token].gate;
      if (gate.kind !== 'runtime') continue;
      expect(gate.reason.length, `${token}: empty reason`).toBeGreaterThan(10);
    }
  });
});

describe('isSectionAvailable', () => {
  it('keeps always-on sections', () => {
    expect(isSectionAvailable({ kind: 'always' }, ALL_AVAILABLE)).toBe(true);
  });

  it('follows the instance flag both ways', () => {
    const gate = { kind: 'instanceFlag', flag: 'openLoopsEnabled' } as const;
    expect(isSectionAvailable(gate, ALL_AVAILABLE)).toBe(true);
    expect(isSectionAvailable(gate, { ...ALL_AVAILABLE, openLoopsEnabled: false })).toBe(false);
  });

  it('shows the user debug panel only to a non-superuser who was granted access', () => {
    const gate = { kind: 'userDebugPanel' } as const;
    expect(isSectionAvailable(gate, ALL_AVAILABLE)).toBe(true);
    // A superuser gets the admin debug section in another tab; the page does not
    // render this one for them at all.
    expect(isSectionAvailable(gate, { ...ALL_AVAILABLE, isSuperuser: true })).toBe(false);
    expect(isSectionAvailable(gate, { ...ALL_AVAILABLE, debugUserAccess: false })).toBe(false);
  });

  it('keeps runtime-gated sections, because absence is not knowable here', () => {
    // The inactive tab is unmounted, so nothing can observe what it would
    // render. Dropping these would turn "empty today" into "does not exist".
    expect(isSectionAvailable({ kind: 'runtime', reason: 'x' }, ALL_AVAILABLE)).toBe(true);
  });
});

describe('buildSettingsSearchIndex', () => {
  it('returns every available section, in page order', () => {
    const index = buildSettingsSearchIndex(echo, ALL_AVAILABLE);
    expect(index.map(entry => entry.token)).toEqual(TOKENS);
  });

  it('drops a section whose instance flag is off', () => {
    const index = buildSettingsSearchIndex(echo, { ...ALL_AVAILABLE, openLoopsEnabled: false });
    expect(index.map(entry => entry.token)).not.toContain('open-loops');
    expect(index).toHaveLength(TOKENS.length - 1);
  });

  it('drops the user debug panel for a superuser', () => {
    const index = buildSettingsSearchIndex(echo, { ...ALL_AVAILABLE, isSuperuser: true });
    expect(index.map(entry => entry.token)).not.toContain('debug-panel');
  });

  it('keeps the sections that may legitimately be absent on arrival', () => {
    // They cannot be filtered out — nothing here can observe the other tab —
    // so the contract is that they are PRESENT in the index; the page tells the
    // reader if the destination turns out not to exist.
    const tokens = buildSettingsSearchIndex(echo, ALL_AVAILABLE).map(entry => entry.token);
    expect(tokens).toContain('telephony-calls');
    expect(tokens).toContain('heartbeat');
    expect(tokens).toContain('security-auth');
  });

  it('folds the group heading into the keyword tier', () => {
    // "Security" is the only word the three security sections share; none of
    // their titles or descriptions contains it.
    const index = buildSettingsSearchIndex(translatorFor('en'), ALL_AVAILABLE);
    const auth = index.find(entry => entry.token === 'security-auth');
    expect(auth?.normalizedKeywords).toContain('security');
  });

  it('rebuilds in the language it is given', () => {
    const fr = buildSettingsSearchIndex(translatorFor('fr'), ALL_AVAILABLE);
    const en = buildSettingsSearchIndex(translatorFor('en'), ALL_AVAILABLE);
    expect(fr.find(entry => entry.token === 'theme')?.title).toBe('Apparence');
    expect(en.find(entry => entry.token === 'theme')?.title).toBe('Appearance');
  });
});

describe('matchSettingsSections — ranking', () => {
  const index = buildSettingsSearchIndex(translatorFor('en'), ALL_AVAILABLE);

  it('returns nothing for an empty or blank query', () => {
    expect(matchSettingsSections(index, '')).toEqual([]);
    expect(matchSettingsSections(index, '   ')).toEqual([]);
    expect(matchSettingsSections(index, '\t\n')).toEqual([]);
  });

  it('puts a title-prefix match above a title-substring match', () => {
    const results = matchSettingsSections(index, 'my');
    // "My devices" and "My Connectors" start with it; "Knowledge Spaces (RAG)"
    // does not contain it at all.
    expect(results[0].title.toLowerCase().startsWith('my')).toBe(true);
    const prefixScore = results[0].score;
    const later = results.find(result => !result.title.toLowerCase().startsWith('my'));
    if (later) expect(later.score).toBeLessThan(prefixScore);
  });

  it('ranks title above keywords above description', () => {
    const results = matchSettingsSections(index, 'notification');
    const tiers = results.map(result => result.matchedIn);
    // Whatever the corpus, the sequence of tiers must be non-increasing.
    const order = { title: 3, keywords: 2, description: 1 } as const;
    for (let i = 1; i < tiers.length; i++) {
      expect(order[tiers[i]], `tier regression at ${i}: ${tiers.join(' > ')}`).toBeLessThanOrEqual(
        order[tiers[i - 1]]
      );
    }
  });

  it('breaks ties in page order', () => {
    const results = matchSettingsSections(index, 'security');
    const positions = results
      .filter(result => result.score === results[0].score)
      .map(result => TOKENS.indexOf(result.token));
    expect(positions).toEqual([...positions].sort((left, right) => left - right));
  });

  it('reports where the match came from, so the row can explain itself', () => {
    const [byTitle] = matchSettingsSections(index, 'timezone');
    expect(byTitle.matchedIn).toBe('title');
    const [byKeyword] = matchSettingsSections(index, 'totp');
    expect(byKeyword.token).toBe('security-auth');
    expect(byKeyword.matchedIn).toBe('keywords');
  });

  it('finds every word of a query, whatever the order', () => {
    // "push notifications" is the title; typing it reversed must still work,
    // otherwise word order is a hidden syntax rule.
    const reversed = matchSettingsSections(index, 'push notification');
    expect(reversed.map(result => result.token)).toContain('notifications');
  });

  it('never truncates the result list', () => {
    // A very common word: whatever it matches, all of it comes back. A silent
    // top-N would read as "nothing else matches".
    const all = matchSettingsSections(index, 'e');
    const manual = index.filter(entry =>
      `${entry.normalizedTitle} ${entry.normalizedKeywords} ${entry.normalizedDescription}`.includes(
        'e'
      )
    );
    expect(all.length).toBe(manual.length);
  });

  it('cannot return a section that was gated out', () => {
    const gated = buildSettingsSearchIndex(echo, { ...ALL_AVAILABLE, openLoopsEnabled: false });
    expect(matchSettingsSections(gated, 'open-loops')).toEqual([]);
  });
});

describe('matchSettingsSections — recall in the six languages', () => {
  /**
   * Each row is a claim about what a reader can find by typing what they think
   * the setting is called. Measured against the real dictionaries: before the
   * keyword lists existed, "sombre", "2FA", "TOTP" and "RGPD" matched nothing
   * at all.
   */
  const CLAIMS: ReadonlyArray<[LocaleCode, string, SettingsSectionToken]> = [
    // The thirteen sections the 17-token table used to miss.
    ['fr', 'thème', 'theme'],
    ['fr', 'langue', 'language'],
    ['fr', 'fuseau horaire', 'timezone'],
    ['fr', 'police', 'font'],
    ['fr', 'mot de passe', 'security-auth'],
    ['fr', 'mes appareils', 'security-devices'],
    ['fr', 'exporter mes données', 'security-export'],
    // Synonyms and acronyms — the whole point of the keyword lists.
    ['fr', 'sombre', 'theme'],
    ['fr', '2FA', 'security-auth'],
    ['fr', 'RGPD', 'security-export'],
    ['fr', 'cron', 'scheduled-actions'],
    ['fr', 'micro', 'voice-mode'],
    // Accent- and apostrophe-insensitivity, typed the way a keyboard emits it.
    ['fr', 'theme', 'theme'],
    ['fr', 'THÈME', 'theme'],
    ['fr', "d'authentification", 'security-auth'],
    ['fr', 'securite', 'security-auth'],
    ['en', 'dark mode', 'theme'],
    ['en', 'password', 'security-auth'],
    ['en', 'gdpr', 'security-export'],
    ['en', 'timezone', 'timezone'],
    ['de', 'Passwort', 'security-auth'],
    ['de', 'Dunkelmodus', 'theme'],
    ['de', 'DSGVO', 'security-export'],
    ['de', 'Zeitzone', 'timezone'],
    ['es', 'contraseña', 'security-auth'],
    ['es', 'modo oscuro', 'theme'],
    ['es', 'zona horaria', 'timezone'],
    ['it', 'password', 'security-auth'],
    ['it', 'modalità scura', 'theme'],
    ['it', 'fuso', 'timezone'],
    ['zh', '主题', 'theme'],
    ['zh', '密码', 'security-auth'],
    ['zh', '时区', 'timezone'],
    ['zh', '语言', 'language'],
  ];

  const indexes = Object.fromEntries(
    (Object.keys(LOCALES) as LocaleCode[]).map(locale => [
      locale,
      buildSettingsSearchIndex(translatorFor(locale), ALL_AVAILABLE),
    ])
  ) as Record<LocaleCode, ReturnType<typeof buildSettingsSearchIndex>>;

  it.each(CLAIMS)('%s: "%s" finds %s', (locale, query, expected) => {
    const results = matchSettingsSections(indexes[locale], query);
    expect(
      results.map(result => result.token),
      `${locale}: "${query}" returned [${results.map(r => r.token).join(', ')}]`
    ).toContain(expected);
  });

  it.each(Object.keys(LOCALES) as LocaleCode[])(
    'every section of the %s index is reachable by its own title',
    locale => {
      // The floor nobody should ever fall through: whatever else fails, typing
      // a section's exact title must find it.
      const index = indexes[locale];
      const unreachable = index
        .filter(
          entry => !matchSettingsSections(index, entry.title).some(r => r.token === entry.token)
        )
        .map(entry => `${entry.token} ("${entry.title}")`);
      expect(unreachable, `unreachable by title: ${unreachable.join(', ')}`).toEqual([]);
    }
  );

  it('does not answer a query that matches nothing', () => {
    expect(matchSettingsSections(indexes.fr, 'zzzqwerty')).toEqual([]);
  });
});

describe('commitments live with the other Features sections', () => {
  it('is grouped under identity_memory, next to interests', () => {
    // Moved out of `personalization` (2026-08-02): a commitments ledger is a
    // capability, not a display preference — it now sits in the Features tab,
    // right after "Centres d'intérêt". The search index is what deep links and
    // the quick search read, so a section shown in one tab and indexed under
    // another sends the user to the wrong place.
    expect(SETTINGS_SEARCH_META['open-loops'].group).toBe('identity_memory');
    expect(SETTINGS_SEARCH_META['open-loops'].group).toBe(SETTINGS_SEARCH_META.interests.group);
  });
});
