/**
 * FAQContent — the searchable help page (chantier couverture, Lot 5).
 *
 * The component is content-driven: with the global i18n stub (which echoes the
 * key) every question count parses to `NaN` and the page renders empty, so the
 * tests would be vacuous. It is therefore driven by a **small realistic
 * dictionary** — accented French with HTML in the answers — which pins the
 * mechanism without coupling the suite to the editorial content:
 *
 *  - matching is accent-insensitive **in both directions** and looks inside the
 *    answers, not just the questions;
 *  - the HTML markup of an answer is stripped before matching, so searching
 *    "strong" must not surface every answer that happens to be bold;
 *  - the highlight re-inserts the **original** accented characters (it maps
 *    normalized positions back), and only ever injects trusted translation
 *    text — the user query feeds an escaped regex and nothing else, which is
 *    what makes the `dangerouslySetInnerHTML` here safe.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

const CONTENT: Record<string, string> = {
  'faq.search.placeholder': 'Rechercher',
  'faq.search.clear': 'Effacer',
  'faq.search.results_count': '{{count}} résultat(s)',
  'faq.search.no_results': 'Aucun résultat pour « {{query}} »',
  'faq.search.no_results_hint': 'Essayez un autre mot',
  'faq.show_welcome': 'Revoir la présentation',
  'faq.intro.title': 'Comment ça marche',
  'faq.changelog.title': 'Nouveautés',
  // Two populated sections; the others keep a non-numeric count, which the
  // component reads as "no question" — the real page has all of them filled.
  'faq.sections.chat.count': '2',
  'faq.sections.chat.title': 'Conversation',
  'faq.try_example': 'Essayer cet exemple : {{example}}',
  'faq.sections.chat.questions.q1.question': 'Comment gérer ma préférence ?',
  // Carries a bulleted command (W1) alongside prose emphasis: only the former
  // becomes clickable.
  'faq.sections.chat.questions.q1.answer':
    '<p>LIA mémorise vos <strong>préférences</strong> de style.</p>' +
    '<br>• «<em>Retiens que je préfère les réponses courtes</em>»' +
    '<br>Dites <em>le premier</em> pour choisir.',
  'faq.sections.chat.questions.q2.question': 'Puis-je interrompre une réponse ?',
  'faq.sections.chat.questions.q2.answer': '<p>Oui, le bouton stop coupe le flux.</p>',
  'faq.sections.privacy.count': '1',
  'faq.sections.privacy.title': 'Confidentialité',
  'faq.sections.privacy.questions.q1.question': 'Mes données sont-elles chiffrées ?',
  'faq.sections.privacy.questions.q1.answer': '<p>Oui, au repos et en transit.</p>',
};

const { translate } = vi.hoisted(() => ({
  translate: (key: string, params?: Record<string, unknown>) => {
    const value = key in CONTENT ? CONTENT[key] : key;
    return params
      ? value.replace(/\{\{(\w+)\}\}/g, (_match, name: string) => String(params[name] ?? ''))
      : value;
  },
}));

// Overrides the global stub for this file only: real text is what makes the
// search, the stripping and the highlighting observable.
vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: translate,
    i18n: { language: 'fr', changeLanguage: vi.fn() },
  }),
}));

// The global stub hands back a FRESH `push` on every `useRouter()` call, so
// the navigation a click triggers would be unobservable. A stable spy is the
// only way to assert where an example actually sends the user.
const { push } = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push,
    replace: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => '/fr/dashboard/faq',
  useSearchParams: () => new URLSearchParams(),
}));

import { FAQContent } from '../FAQContent';

function render(props: Partial<Parameters<typeof FAQContent>[0]> = {}) {
  return renderWithProviders(<FAQContent lng="fr" {...props} />);
}

const searchBox = () => screen.getByRole('textbox', { name: 'Rechercher' });

/**
 * A question, addressed through its accordion trigger. While searching the
 * label is split by the `<mark>` elements, so a text query would miss it — the
 * accessible name concatenates the fragments back.
 */
const question = (label: string) => screen.queryByRole('button', { name: label });

/** The "nothing found" wording appears twice: summary line + empty card. */
const noResults = (pattern: RegExp | string) => screen.getAllByText(pattern);

async function search(user: ReturnType<typeof render>['user'], query: string) {
  await user.type(searchBox(), query);
}

beforeEach(() => vi.clearAllMocks());

describe('FAQContent — browsing', () => {
  it('lists the questions of the populated sections', () => {
    render();

    expect(screen.getByText('Comment gérer ma préférence ?')).toBeInTheDocument();
    expect(screen.getByText('Puis-je interrompre une réponse ?')).toBeInTheDocument();
    expect(screen.getByText('Mes données sont-elles chiffrées ?')).toBeInTheDocument();
  });

  it('keeps the intro and the changelog folded until they are opened', async () => {
    const { user } = render();
    const intro = screen.getByRole('button', { name: /Comment ça marche/ });

    expect(intro).toBeInTheDocument();
    await user.click(intro);
    await user.click(screen.getByRole('button', { name: /Nouveautés/ }));

    // Both toggles stay reachable after being opened (no crash on the
    // content-driven grids they reveal).
    expect(screen.getByRole('button', { name: /Comment ça marche/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Nouveautés/ })).toBeInTheDocument();
  });

  it('offers the welcome tour only when the page can actually show it', async () => {
    const onShowWelcome = vi.fn();
    const { unmount } = render({ showWelcomeButton: true, onShowWelcome });
    expect(screen.getByRole('button', { name: /Revoir la présentation/ })).toBeInTheDocument();
    unmount();

    render({ showWelcomeButton: true });
    expect(
      screen.queryByRole('button', { name: /Revoir la présentation/ })
    ).not.toBeInTheDocument();
  });

  it('replays the welcome tour on demand', async () => {
    const onShowWelcome = vi.fn();
    const { user } = render({ showWelcomeButton: true, onShowWelcome });

    await user.click(screen.getByRole('button', { name: /Revoir la présentation/ }));

    expect(onShowWelcome).toHaveBeenCalledTimes(1);
  });
});

describe('FAQContent — searching', () => {
  it('keeps only the matching question and announces the count', async () => {
    const { user } = render();

    await search(user, 'interrompre');

    expect(question('Puis-je interrompre une réponse ?')).toBeInTheDocument();
    expect(question('Comment gérer ma préférence ?')).not.toBeInTheDocument();
    expect(question('Mes données sont-elles chiffrées ?')).not.toBeInTheDocument();
    expect(screen.getByText('1 résultat(s)')).toBeInTheDocument();
  });

  it('hides the intro and changelog panels while searching', async () => {
    const { user } = render();
    await search(user, 'interrompre');

    expect(screen.queryByRole('button', { name: /Comment ça marche/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Nouveautés/ })).not.toBeInTheDocument();
  });

  it('matches an unaccented query against accented content', async () => {
    const { user } = render();

    await search(user, 'preference');

    expect(question('Comment gérer ma préférence ?')).toBeInTheDocument();
  });

  it('matches an accented query against the same content', async () => {
    const { user } = render();

    await search(user, 'préférence');

    expect(question('Comment gérer ma préférence ?')).toBeInTheDocument();
  });

  it('searches the answers too, not only the questions', async () => {
    const { user } = render();

    // "stop" appears in q2's answer and in no question.
    await search(user, 'stop');

    expect(question('Puis-je interrompre une réponse ?')).toBeInTheDocument();
    expect(screen.getByText('1 résultat(s)')).toBeInTheDocument();
  });

  it('does not let the HTML of an answer become searchable', async () => {
    const { user } = render();

    // `<strong>` wraps a word in q1's answer: the tag itself must be invisible
    // to the search, otherwise every emphasised answer would match.
    await search(user, 'strong');

    expect(noResults(/Aucun résultat pour/).length).toBeGreaterThan(0);
  });

  it('says nothing was found, quoting the query back', async () => {
    const { user } = render();

    await search(user, 'zzzz');

    // Summary line and empty card carry the same wording, query included.
    expect(noResults('Aucun résultat pour « zzzz »')).toHaveLength(2);
    expect(screen.getByText('Essayez un autre mot')).toBeInTheDocument();
  });

  it('restores the whole page when the search is cleared', async () => {
    const { user } = render();
    await search(user, 'interrompre');
    expect(question('Mes données sont-elles chiffrées ?')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Effacer' }));

    expect(searchBox()).toHaveValue('');
    expect(question('Mes données sont-elles chiffrées ?')).toBeInTheDocument();
  });
});

describe('FAQContent — highlighting', () => {
  it('marks the match with the original accents preserved', async () => {
    const { user, container } = render();

    await search(user, 'preference');

    const marks = Array.from(container.querySelectorAll('mark'));
    expect(marks.length).toBeGreaterThan(0);
    // The query was unaccented; what is highlighted is the source text, at the
    // right offsets — this is the position mapping doing its job.
    expect(marks.map(m => m.textContent)).toContain('préférence');
  });

  it('never injects the user query into the page', async () => {
    const { user, container } = render();

    await search(user, '<img src=x onerror="alert(1)">');

    expect(container.querySelector('img')).toBeNull();
    expect(noResults(/Aucun résultat pour/).length).toBeGreaterThan(0);
  });

  it('treats a regex-special query as literal text', async () => {
    const { user } = render();

    // An unescaped `?` or `(` in the highlight regex would throw and blank the
    // page; `.*` would match everything.
    await search(user, 'chiffrées ?');

    expect(screen.getByText('1 résultat(s)')).toBeInTheDocument();
    expect(question('Mes données sont-elles chiffrées ?')).toBeInTheDocument();
  });
});

describe('FAQContent — actionable examples (W1)', () => {
  /** Open the accordion holding the bulleted command. */
  async function openExampleQuestion(user: ReturnType<typeof render>['user']) {
    await user.click(question('Comment gérer ma préférence ?')!);
  }

  it('sends a clicked example to the chat as a prefilled draft', async () => {
    const { user } = render();
    await openExampleQuestion(user);

    await user.click(
      screen.getByRole('button', { name: /Retiens que je préfère les réponses courtes/ })
    );

    // Prefilled, NEVER sent: the user lands in the composer with the phrase
    // ready to read, edit or discard.
    expect(push).toHaveBeenCalledWith(
      `/fr/dashboard/chat?draft=${encodeURIComponent('Retiens que je préfère les réponses courtes')}`
    );
  });

  it('keeps prose emphasis inert', async () => {
    const { user } = render();
    await openExampleQuestion(user);

    expect(screen.queryByRole('button', { name: /^le premier$/ })).not.toBeInTheDocument();
    expect(screen.getByText('le premier')).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it('keeps the answer formatting around the examples', async () => {
    const { user } = render();
    await openExampleQuestion(user);

    // The split must not swallow the surrounding markup.
    expect(screen.getByText('préférences')).toBeInTheDocument();
  });

  it('still works on a highlighted answer while searching', async () => {
    // Searching rewrites the answer HTML with <mark> before it reaches the
    // splitter — the commands must survive that rewrite. Search does NOT
    // auto-expand the matches, so the journey is: search, open, act.
    const { user } = render();
    await search(user, 'préférence');
    await openExampleQuestion(user);

    const example = screen.getByRole('button', {
      name: /Retiens que je préfère les réponses courtes/,
    });
    await user.click(example);

    expect(push).toHaveBeenCalledWith(
      `/fr/dashboard/chat?draft=${encodeURIComponent('Retiens que je préfère les réponses courtes')}`
    );
  });
});
