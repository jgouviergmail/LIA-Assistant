/**
 * The home page's pitch as language-neutral data: who is compared, on which
 * criteria and with which status. Every word lives in the locales. The browser
 * imports this module through the comparison explorer, so it names the
 * comparison's keys alone: the positioning and the arguments are rendered on
 * the server, and their subtrees never reach the browser
 * (`i18n/scoped-translations.ts`).
 *
 * LIA always faces ONE contender at a time: a four-column table was
 * unreadable (owner, 2026-11-15).
 *
 * A competitor statement is a claim about someone else's product: each one was
 * read in that product's own documentation and official announcements
 * on `COMPARISON_SOURCES_READ_ON`, and the page says
 * so under the table (docs/technical/LANDING_PAGE.md). A status is changed with
 * its sentences, in the six locales, never alone.
 */

import { LOCALE_MAP, type Language } from '@/i18n/settings';

export const CONTENDER_IDS = ['lia', 'openclaw', 'hermes', 'muse'] as const;
export type ContenderId = (typeof CONTENDER_IDS)[number];
export type CompetitorId = Exclude<ContenderId, 'lia'>;
export const COMPETITOR_IDS: readonly CompetitorId[] = ['openclaw', 'hermes', 'muse'];

/** Proper names: the same in every language. */
export const CONTENDER_NAMES: Readonly<Record<ContenderId, string>> = {
  lia: 'LIA',
  openclaw: 'OpenClaw',
  hermes: 'Hermes Agent',
  muse: 'Meta Muse',
};

/**
 * Each product's own mark, served from this application (`public/`), never
 * fetched from a vendor. The three third-party files are the icons their
 * publishers serve on their own websites, read on 2026-11-15: openclaw.ai
 * `/favicon.svg` and muse.ai `/images/favicon/app-squiggle.svg` copied
 * unchanged, the Hermes Agent documentation's `/docs/img/logo.png`
 * downscaled to 128 px. Trademarks of their owners (NOTICE.md).
 */
export const CONTENDER_MARKS: Readonly<Record<ContenderId, string>> = {
  lia: '/v4-lia-brain.svg',
  openclaw: '/comparison-icons/openclaw.svg',
  hermes: '/comparison-icons/hermes-agent.png',
  muse: '/comparison-icons/meta-muse.svg',
};

/** The duel buttons' names: three of them hold one line on a 320 px phone. */
export const CONTENDER_SHORT_NAMES: Readonly<Record<CompetitorId, string>> = {
  openclaw: 'OpenClaw',
  hermes: 'Hermes',
  muse: 'Muse',
};

/** LIA's cells say a little more: three lines against two. */
export const BULLETS_PER_CONTENDER: Readonly<Record<ContenderId, number>> = {
  lia: 3,
  openclaw: 2,
  hermes: 2,
  muse: 2,
};

export type ComparisonStatus = 'yes' | 'mid' | 'no';

export const CRITERION_IDS = ['agentic', 'daily', 'family', 'voice', 'memory', 'admin'] as const;
export type CriterionId = (typeof CRITERION_IDS)[number];

export interface Criterion {
  id: CriterionId;
  status: Readonly<Record<ContenderId, ComparisonStatus>>;
}

export const CRITERIA: readonly Criterion[] = [
  { id: 'agentic', status: { lia: 'yes', openclaw: 'yes', hermes: 'yes', muse: 'yes' } },
  { id: 'daily', status: { lia: 'yes', openclaw: 'mid', hermes: 'mid', muse: 'mid' } },
  { id: 'family', status: { lia: 'yes', openclaw: 'mid', hermes: 'mid', muse: 'no' } },
  { id: 'voice', status: { lia: 'yes', openclaw: 'yes', hermes: 'yes', muse: 'mid' } },
  { id: 'memory', status: { lia: 'yes', openclaw: 'mid', hermes: 'mid', muse: 'mid' } },
  { id: 'admin', status: { lia: 'yes', openclaw: 'mid', hermes: 'mid', muse: 'no' } },
];

/** The five argument tiles, in reading order. */
export const ARGUMENT_IDS = ['agentic', 'manual', 'family', 'voice', 'governance'] as const;
export type ArgumentId = (typeof ARGUMENT_IDS)[number];

/** The day the competitors' statements were read, shown under the table. */
export const COMPARISON_SOURCES_READ_ON = '2026-11-16';

/**
 * The reading day in the page's language. A calendar day, not an instant: read
 * in UTC so no zone moves it. Formatted ONCE, by the server section, so the
 * browser never re-formats it with ICU data of its own.
 */
export function formatSourcesReadOn(lng: Language): string {
  return new Intl.DateTimeFormat(LOCALE_MAP[lng], { dateStyle: 'long', timeZone: 'UTC' }).format(
    new Date(`${COMPARISON_SOURCES_READ_ON}T00:00:00Z`)
  );
}

export const COMPARISON_SOURCES = [
  { key: 'openclaw', href: 'https://docs.openclaw.ai/' },
  { key: 'openclaw_multiplayer', href: 'https://docs.openclaw.ai/start/multiplayer' },
  { key: 'hermes', href: 'https://hermes-agent.nousresearch.com/docs' },
  {
    key: 'muse_announcement',
    href: 'https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/',
  },
  {
    key: 'muse_spaces',
    href: 'https://about.fb.com/news/2026/11/introducing-spaces-customize-muse-app/',
  },
  {
    key: 'muse_voice',
    href: 'https://about.fb.com/news/2026/11/introducing-muse-ai-voice-expressive-avatars/',
  },
  {
    key: 'muse_design',
    href: 'https://muse.ai/blog/how-we-designed-muse',
  },
] as const;

/** Where a reader reports a statement that went stale. */
export const COMPARISON_REPORT_URL = 'https://github.com/jgouviergmail/LIA-Assistant/issues';

const COMPARISON = 'landing.comparison';

/** One cell's keys: a head line, its bullets, its punchline. */
export function cellKeys(
  criterion: CriterionId,
  contender: ContenderId
): { head: string; bullets: string[]; punch: string } {
  const base = `${COMPARISON}.rows.${criterion}.${contender}`;
  return {
    head: `${base}.head`,
    bullets: Array.from(
      { length: BULLETS_PER_CONTENDER[contender] },
      (_, index) => `${base}.b${index + 1}`
    ),
    punch: `${base}.punch`,
  };
}
