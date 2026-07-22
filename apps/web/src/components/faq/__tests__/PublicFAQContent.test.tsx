/**
 * PublicFAQContent — the landing FAQ for signed-out visitors.
 *
 * Same testing approach as FAQContent.test.tsx: the component is content-
 * driven, so a small realistic dictionary (accented French, HTML answers, one
 * answer in the grouped `<br><br><strong>` shape) makes the mechanisms
 * observable without coupling the suite to the editorial content:
 *
 *  - only the public section subset renders, with an anchor rail entry per
 *    section;
 *  - search is accent-insensitive, looks inside answers, auto-opens matches
 *    and highlights the original characters;
 *  - a grouped answer renders as per-domain sub-accordions whose text
 *    preserves every word of the source; while searching it falls back to the
 *    flat (highlightable) rendering.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

const GROUPED_ANSWER =
  'Des exemples concrets :' +
  '<br><br><strong>🌐 MULTI DOMAINES</strong><br>• "<em>Prépare ma journée</em>"<br>• "<em>Trouve un créneau</em>"' +
  '<br><br><strong>📧 EMAILS</strong><br>• "<em>Réponds à Sébastien</em>"' +
  '<br><br><strong>📅 AGENDA</strong><br>• "<em>Décale mon rendez-vous</em>"';

const CONTENT: Record<string, string> = {
  'faq.title': 'Questions fréquentes',
  'faq.search.placeholder': 'Rechercher',
  'faq.search.clear': 'Effacer',
  'faq.search.results_count': '{{count}} résultat(s)',
  'faq.search.no_results': 'Aucun résultat pour « {{query}} »',
  'faq.search.no_results_hint': 'Essayez un autre mot',
  'faq.sections.getting_started.count': '2',
  'faq.sections.getting_started.title': 'Démarrage',
  'faq.sections.getting_started.description': 'Commencer avec LIA',
  'faq.sections.getting_started.questions.q1.question': 'Qu’est-ce que LIA ?',
  'faq.sections.getting_started.questions.q1.answer':
    '<p>Votre assistant <strong>personnel</strong> avec un <a href="/why">manifeste</a>.</p>',
  'faq.sections.getting_started.questions.q2.question': 'Que puis-je demander ?',
  'faq.sections.getting_started.questions.q2.answer': GROUPED_ANSWER,
  'faq.sections.privacy.count': '1',
  'faq.sections.privacy.title': 'Confidentialité',
  'faq.sections.privacy.description': 'Vos données',
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

vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: translate,
    i18n: { language: 'fr', changeLanguage: vi.fn() },
  }),
}));

import { PublicFAQContent } from '../PublicFAQContent';

function render() {
  return renderWithProviders(<PublicFAQContent lng="fr" />);
}

const searchBox = () => screen.getByRole('textbox', { name: 'Rechercher' });

beforeEach(() => vi.clearAllMocks());

describe('PublicFAQContent — browsing', () => {
  it('renders the populated public sections with their questions folded', () => {
    render();

    expect(screen.getByRole('heading', { name: 'Démarrage' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Confidentialité' })).toBeInTheDocument();

    const q1 = screen.getByText('Qu’est-ce que LIA ?');
    expect(q1.closest('details')).not.toHaveAttribute('open');
    expect(screen.getByText('Mes données sont-elles chiffrées ?')).toBeInTheDocument();
  });

  it('offers one anchor-rail link per public section, pointing at its heading', () => {
    render();

    const nav = screen.getByRole('navigation', { name: 'Questions fréquentes' });
    const links = Array.from(nav.querySelectorAll('a'));
    expect(links.length).toBeGreaterThanOrEqual(6);
    expect(links.map(a => a.getAttribute('href'))).toContain('#faq-getting_started');
    expect(links.map(a => a.getAttribute('href'))).toContain('#faq-privacy');
    // Each anchor resolves to a real heading section in the document.
    expect(document.getElementById('faq-getting_started')).not.toBeNull();
    expect(document.getElementById('faq-privacy')).not.toBeNull();
  });

  it('renders a grouped answer as per-domain sub-accordions preserving the words', () => {
    render();

    // Group headings become summaries…
    expect(screen.getByText('🌐 MULTI DOMAINES')).toBeInTheDocument();
    expect(screen.getByText('📧 EMAILS')).toBeInTheDocument();
    expect(screen.getByText('📅 AGENDA')).toBeInTheDocument();
    // …and every bullet keeps its text (list items, no bullet glyphs lost).
    expect(screen.getByText('Prépare ma journée')).toBeInTheDocument();
    expect(screen.getByText('Trouve un créneau')).toBeInTheDocument();
    expect(screen.getByText('Réponds à Sébastien')).toBeInTheDocument();
    expect(screen.getByText('Décale mon rendez-vous')).toBeInTheDocument();
  });
});

describe('PublicFAQContent — search', () => {
  it('filters accent-insensitively, counts results and auto-opens matches', async () => {
    const { user } = render();

    await user.type(searchBox(), 'chiffrees');

    expect(screen.getByText('1 résultat(s)')).toBeInTheDocument();
    const match = screen.getByText(/Mes données sont-elles/);
    expect(match.closest('details')).toHaveAttribute('open');
    // Non-matching sections disappear entirely.
    expect(screen.queryByText('Qu’est-ce que LIA ?')).not.toBeInTheDocument();
    expect(screen.queryByText('Démarrage')).not.toBeInTheDocument();
  });

  it('matches inside answers and highlights the original accented text', async () => {
    const { user } = render();

    await user.type(searchBox(), 'sebastien');

    // The grouped answer matched through its text: flat rendering + highlight.
    const mark = document.querySelector('mark');
    expect(mark).not.toBeNull();
    expect(mark!.textContent).toBe('Sébastien');
    // Grouped sub-accordions are suspended while searching (flat HTML only,
    // so the highlight can never hide inside a collapsed group).
    expect(document.querySelectorAll('details details')).toHaveLength(0);
  });

  it('shows the empty state and recovers when the query is cleared', async () => {
    const { user } = render();

    await user.type(searchBox(), 'zzzznothing');
    expect(screen.getAllByText(/Aucun résultat pour/).length).toBeGreaterThanOrEqual(1);

    await user.click(screen.getByTitle('Effacer'));
    expect(screen.getByText('Qu’est-ce que LIA ?')).toBeInTheDocument();
  });
});
