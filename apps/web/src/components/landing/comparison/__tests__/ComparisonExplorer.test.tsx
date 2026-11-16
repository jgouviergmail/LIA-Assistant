/**
 * The comparison arena, read through its real words: LIA always faces ONE
 * challenger (a four-way table was unreadable, owner 2026-11-15); the
 * challenger tiles move the stage, the criteria and their caption together;
 * every criterion says everything at once — status in words, head line,
 * punchline and facts — with no reading filter and no fold (owner,
 * 2026-11-15: « afficher tout », « toujours afficher les faits »); each product
 * shows its own mark.
 *
 * The criteria are ONE structure at every width — a list of headed items, one
 * named group per contender, laid out in columns from `lg` by CSS alone — so
 * every sentence is rendered once, never once per layout.
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import { describe, expect, it, vi } from 'vitest';

import en from '../../../../../locales/en/translation.json';
import fr from '../../../../../locales/fr/translation.json';

import { ComparisonExplorer } from '../ComparisonExplorer';
import { CONTENDER_IDS, CRITERION_IDS, formatSourcesReadOn } from '../comparison-data';

vi.unmock('react-i18next');

const WORDS = { fr: fr.landing.comparison, en: en.landing.comparison } as const;

type Words = (typeof WORDS)[keyof typeof WORDS];

async function renderExplorer(lng: 'fr' | 'en' = 'fr') {
  const i18n = createInstance();
  await i18n.init({
    lng,
    resources: { fr: { translation: fr }, en: { translation: en } },
    interpolation: { escapeValue: false },
  });
  const user = userEvent.setup();
  render(
    <I18nextProvider i18n={i18n}>
      <ComparisonExplorer readOn={formatSourcesReadOn(lng)} />
    </I18nextProvider>
  );
  const words = WORDS[lng];
  return {
    user,
    words,
    challengers: screen.getByRole('group', { name: words.view_label }),
    stage: () => screen.getByRole('group', { name: words.contenders_label }),
  };
}

/** The criteria of one duel, named by its caption. */
function criteriaOf(words: Words, rival: string): HTMLElement {
  return screen.getByRole('list', { name: words.caption.replace('{{name}}', rival) });
}

/** The item a criterion heads. */
function itemOf(list: HTMLElement, label: string): HTMLElement {
  const item = within(list).getByRole('heading', { level: 3, name: label }).closest('li');
  if (!item) throw new Error(`The ${label} criterion must head a list item`);
  return item;
}

/** Who speaks in an item, in reading order. */
function contendersOf(item: HTMLElement): string[] {
  return within(item)
    .getAllByRole('group')
    .map(group => group.getAttribute('aria-label') ?? '');
}

describe('ComparisonExplorer', () => {
  it('opens on LIA facing OpenClaw, never on four contenders at once', async () => {
    const { challengers, words } = await renderExplorer();
    const tiles = within(challengers).getAllByRole('button');
    expect(tiles).toHaveLength(3);
    ['OpenClaw', 'Hermes', 'Muse'].forEach((name, index) =>
      expect(tiles[index]).toHaveAccessibleName(name)
    );
    expect(within(challengers).getByRole('button', { name: 'OpenClaw' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    // One item per criterion, each headed by it (the facts nest lists of their own).
    const items = within(criteriaOf(words, 'OpenClaw'))
      .getAllByRole('heading', { level: 3 })
      .map(heading => itemOf(criteriaOf(words, 'OpenClaw'), heading.textContent ?? ''));
    expect(items).toHaveLength(CRITERION_IDS.length);
    for (const item of items) expect(contendersOf(item)).toEqual(['LIA', 'OpenClaw']);
  });

  it('asks nothing but the duel: the three challenger tiles are its only controls', async () => {
    const { challengers } = await renderExplorer();
    expect(screen.getAllByRole('button')).toEqual(within(challengers).getAllByRole('button'));
  });

  it('says everything at once: status, head line, punchline and every fact', async () => {
    const { words } = await renderExplorer();
    const list = criteriaOf(words, 'OpenClaw');
    for (const id of CRITERION_IDS) {
      const item = itemOf(list, words.rows[id].label);
      for (const [index, contender] of (['lia', 'openclaw'] as const).entries()) {
        const says = within(item).getAllByRole('group')[index];
        const cell = words.rows[id][contender] as Readonly<Record<string, string>>;
        for (const line of Object.values(cell)) expect(within(says).getByText(line)).toBeVisible();
      }
    }
  });

  it('renders each sentence once, whatever the width', async () => {
    const { words } = await renderExplorer();
    for (const id of CRITERION_IDS) {
      expect(screen.getAllByRole('heading', { level: 3, name: words.rows[id].label })).toHaveLength(
        1
      );
      expect(screen.getAllByText(words.rows[id].lia.head)).toHaveLength(1);
      expect(screen.getAllByText(words.rows[id].openclaw.b1)).toHaveLength(1);
    }
    // The column header row of a wide screen is a picture of the groups' names.
    expect(screen.getByText(words.criterion_header).closest('[aria-hidden="true"]')).not.toBeNull();
  });

  it('moves the stage, the criteria and their caption together when the challenger changes', async () => {
    const { user, challengers, stage, words } = await renderExplorer();
    const hermes = within(challengers).getByRole('button', { name: 'Hermes' });
    await user.click(hermes);
    expect(hermes).toHaveAttribute('aria-pressed', 'true');
    expect(within(challengers).getByRole('button', { name: 'OpenClaw' })).toHaveAttribute(
      'aria-pressed',
      'false'
    );
    const item = itemOf(criteriaOf(words, 'Hermes Agent'), words.rows.agentic.label);
    expect(contendersOf(item)).toEqual(['LIA', 'Hermes Agent']);
    expect(within(item).getByText(words.rows.agentic.hermes.b1)).toBeInTheDocument();
    expect(within(item).queryByText(words.rows.agentic.openclaw.head)).not.toBeInTheDocument();
    const cards = within(stage()).getAllByRole('article');
    expect(cards.map(card => card.getAttribute('aria-label'))).toEqual(['LIA', 'Hermes Agent']);
    expect(within(stage()).getByText(words.contenders.hermes.quote)).toBeInTheDocument();
    expect(within(stage()).queryByText(words.contenders.openclaw.quote)).not.toBeInTheDocument();
  });

  it('says every status in words, not only by colour', async () => {
    const { user, challengers, words } = await renderExplorer();
    await user.click(within(challengers).getByRole('button', { name: 'Muse' }));
    const statusWords = new Set(Object.values(words.status));
    const said = within(itemOf(criteriaOf(words, 'Meta Muse'), words.rows.family.label))
      .getAllByRole('group')
      .map(group =>
        within(group)
          .getAllByText(text => statusWords.has(text))
          .map(node => node.textContent)
      );
    expect(said).toEqual([[words.status.yes], [words.status.no]]);
  });

  it('marks each contender with its own product icon, decoratively', async () => {
    const { challengers, stage, words } = await renderExplorer();
    const marks = (scope: Element) =>
      Array.from(scope.querySelectorAll('img')).map(image => image.getAttribute('src'));
    expect(marks(challengers)).toEqual([
      '/comparison-icons/openclaw.svg',
      '/comparison-icons/hermes-agent.png',
      '/comparison-icons/meta-muse.svg',
    ]);
    expect(marks(stage())).toEqual(['/v4-lia-brain.svg', '/comparison-icons/openclaw.svg']);
    expect(marks(itemOf(criteriaOf(words, 'OpenClaw'), words.rows.voice.label))).toEqual([
      '/v4-lia-brain.svg',
      '/comparison-icons/openclaw.svg',
    ]);
    for (const image of Array.from(document.querySelectorAll('img'))) {
      expect(image).toHaveAttribute('alt', '');
    }
  });

  it('keeps the criteria to words: no link overloads them', async () => {
    const { words } = await renderExplorer();
    expect(within(criteriaOf(words, 'OpenClaw')).queryAllByRole('link')).toHaveLength(0);
  });

  it('knows every contender it can stage', () => {
    expect(CONTENDER_IDS).toEqual(['lia', 'openclaw', 'hermes', 'muse']);
  });

  it.each([
    ['fr', '16 novembre 2026'],
    ['en', 'November 16, 2026'],
  ] as const)('dates its sources in the page’s language (%s)', async (lng, date) => {
    await renderExplorer(lng);
    expect(screen.getByText(new RegExp(date))).toBeInTheDocument();
    expect(screen.getByRole('link', { name: WORDS[lng].sources.openclaw })).toHaveAttribute(
      'href',
      'https://docs.openclaw.ai/'
    );
  });
});
