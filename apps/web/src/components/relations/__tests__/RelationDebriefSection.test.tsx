/**
 * The debrief section — five states, and the two that are easy to get wrong.
 *
 * A refresh is not a first load: it announces itself with `aria-busy` and never
 * unmounts the text the reader may be halfway through. And a refresh that
 * FAILED must leave the previous debrief standing — replacing a usable synthesis
 * with an empty panel turns "I could not refresh this" into "there is nothing",
 * which is a different, false answer.
 */

import { describe, expect, it, vi } from 'vitest';

import { RelationDebriefSection } from '@/components/relations/RelationDebriefSection';
import type { DebriefStatus, RelationDebrief } from '@/hooks/useRelations';
import { renderWithProviders, screen, within } from '@/__tests__/test-utils';

// The account state a fresh reader has: `tokens_display_enabled` is FALSE by
// default. The badge is mounted anyway — see "what the synthesis cost" below —
// and this mock exists so that re-introducing the gate fails as an assertion
// rather than as a missing AuthProvider.
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { tokens_display_enabled: false } }),
}));

type Props = React.ComponentProps<typeof RelationDebriefSection>;

function debrief(over: Partial<RelationDebrief> = {}): RelationDebrief {
  return {
    status: 'ready',
    person: 'Gérard Dupont',
    body: {
      headline: 'Vous lui devez une réponse.',
      where_we_stand: 'Deux échanges cette semaine.',
      open_points: ['Répondre au devis'],
      suggested_next_step: 'Lui envoyer le devis signé.',
      notable_facts: ['Architecte chez ACME'],
    },
    generated_at: '2026-09-07T06:30:00Z',
    generated_for: '2026-09-07',
    sections_used: ['open_commitments'],
    unavailable: [],
    usage: {
      tokens_in: 1234,
      tokens_out: 567,
      tokens_cache: 0,
      cost_eur: 0.0021,
      model_name: 'gpt-4.1-mini',
    },
    can_rebuild: true,
    ...over,
  };
}

function props(over: Partial<Props> = {}): Props {
  return {
    debrief: debrief(),
    loading: false,
    building: false,
    enabled: true,
    lng: 'fr',
    onRebuild: vi.fn(),
    onToggle: vi.fn(),
    ...over,
  };
}

function render(over: Partial<Props> = {}) {
  // The suite's i18n stub echoes KEYS, so every string oracle below is the key
  // itself. That is the stronger assertion anyway: it proves the component
  // resolves from the locale rather than carrying prose of its own.
  return renderWithProviders(<RelationDebriefSection {...props(over)} />);
}

const TITLE = { name: /relations\.debrief_title/ };

describe('RelationDebriefSection', () => {
  it('renders the synthesis, field by field', () => {
    render();

    expect(screen.getByText('Vous lui devez une réponse.')).toBeInTheDocument();
    expect(screen.getByText('Deux échanges cette semaine.')).toBeInTheDocument();
    expect(screen.getByText(/Répondre au devis/)).toBeInTheDocument();
    expect(screen.getByText(/Lui envoyer le devis signé/)).toBeInTheDocument();
    expect(screen.getByText(/Architecte chez ACME/)).toBeInTheDocument();
  });

  it('states WHEN it was written — a synthesis without its date is a claim about now', () => {
    render();
    const section = screen.getByRole('region', TITLE);
    expect(within(section).getByText(/relations\.debrief_written_at/)).toBeInTheDocument();
  });

  it('names what could not be read rather than implying it away', () => {
    render({ debrief: debrief({ unavailable: ['emails', 'events'] }) });
    expect(screen.getByText(/relations\.debrief_unavailable/)).toBeInTheDocument();
  });

  it('says nothing about gaps when there are none', () => {
    render();
    expect(screen.queryByText(/relations\.debrief_unavailable/)).not.toBeInTheDocument();
  });

  it('renders no heading for a field the model left empty', () => {
    render({
      debrief: debrief({
        body: {
          headline: 'Rien d’ouvert.',
          where_we_stand: 'Calme.',
          open_points: [],
          suggested_next_step: null,
          notable_facts: [],
        },
      }),
    });

    expect(screen.getByText('Rien d’ouvert.')).toBeInTheDocument();
    expect(screen.queryByText('relations.debrief_open_points')).not.toBeInTheDocument();
    expect(screen.queryByText('relations.debrief_next_step')).not.toBeInTheDocument();
  });

  describe('a refresh is not a first load', () => {
    it('announces itself and keeps the previous text on screen', () => {
      render({ building: true });

      const section = screen.getByRole('region', TITLE);
      expect(section).toHaveAttribute('aria-busy', 'true');
      // The very thing a spinner-instead-of-content would have destroyed.
      expect(screen.getByText('Vous lui devez une réponse.')).toBeInTheDocument();
    });

    it('stages a skeleton only for the FIRST read', () => {
      render({ loading: true, debrief: null });
      expect(screen.queryByText('Vous lui devez une réponse.')).not.toBeInTheDocument();
      expect(screen.getByRole('region', TITLE)).toHaveAttribute('aria-busy', 'true');
    });
  });

  describe('a failed refresh leaves the previous debrief standing', () => {
    it('keeps the text and says the refresh failed', () => {
      render({ debrief: debrief({ status: 'failed' }) });

      expect(screen.getByText('Vous lui devez une réponse.')).toBeInTheDocument();
      expect(screen.getByText('relations.debrief_refresh_failed')).toBeInTheDocument();
    });

    it('says so plainly when there was nothing to keep', () => {
      render({ debrief: debrief({ status: 'failed', body: null }) });

      expect(screen.getByText('relations.debrief_failed')).toBeInTheDocument();
    });
  });

  it('separates "nothing to summarise" from "not built yet"', () => {
    render({ debrief: debrief({ status: 'empty', body: null }) });
    expect(screen.getByText('relations.debrief_empty')).toBeInTheDocument();

    render({ debrief: debrief({ status: 'absent', body: null }) });
    expect(screen.getByText('relations.debrief_absent')).toBeInTheDocument();
  });

  describe('the rebuild control', () => {
    it('asks for a rebuild when pressed', async () => {
      const onRebuild = vi.fn();
      const { user } = render({ onRebuild });

      await user.click(screen.getByRole('button', { name: /relations\.debrief_rebuild/ }));
      expect(onRebuild).toHaveBeenCalledOnce();
    });

    it('is reachable by keyboard', async () => {
      const onRebuild = vi.fn();
      const { user } = render({ onRebuild });

      screen.getByRole('button', { name: /relations\.debrief_rebuild/ }).focus();
      await user.keyboard('{Enter}');
      expect(onRebuild).toHaveBeenCalledOnce();
    });

    it('stays focusable while refused — the GUARD prevents the second press', async () => {
      const onRebuild = vi.fn();
      const { user } = render({ onRebuild, debrief: debrief({ can_rebuild: false }) });

      const button = screen.getByRole('button', { name: /relations\.debrief_rebuild/ });
      // `disabled` would blur it and drop it from the tab order (ADR-206).
      expect(button).not.toBeDisabled();
      expect(button).toHaveAttribute('aria-disabled', 'true');
      await user.click(button);
      expect(onRebuild).not.toHaveBeenCalled();
    });
  });

  describe('the account can turn it off', () => {
    it('collapses to a row that turns it back on — never a vanished feature', () => {
      render({ enabled: false });

      expect(screen.getByText('relations.debrief_disabled')).toBeInTheDocument();
      expect(screen.getByRole('switch', { name: /relations\.debrief_switch/ })).toBeInTheDocument();
      expect(screen.queryByText('Vous lui devez une réponse.')).not.toBeInTheDocument();
    });

    it('reports the switch being flipped', async () => {
      const onToggle = vi.fn();
      const { user } = render({ onToggle });

      await user.click(screen.getByRole('switch', { name: /relations\.debrief_switch/ }));
      expect(onToggle).toHaveBeenCalledWith(false);
    });
  });

  it('carries no prose of its own — every string comes from the locale', () => {
    const { container } = render();
    // With the key-echoing stub, anything the component says itself would show
    // up as text that is neither a `relations.*` key nor one of the fixture's
    // model-authored sentences. This is the six-locale contract, checked where
    // it can actually be broken.
    const written = debrief().body!;
    const modelProse = new Set([
      written.headline,
      written.where_we_stand,
      written.suggested_next_step ?? '',
      ...written.open_points,
      ...written.notable_facts,
    ]);
    // The two key namespaces this section legitimately mounts: its own, and the
    // shared usage badge's. Anything else bearing a LETTER would be prose the
    // component wrote itself; a cost formatted by `Intl` bears none, so it is
    // let through by that test rather than by an exception carved for it.
    const keys = ['relations.', 'common.llm_usage.'];
    const stray = Array.from(container.querySelectorAll('p, span, li, h3, h4, label'))
      .map(node => node.textContent?.trim() ?? '')
      .filter(text => text.length > 0)
      .filter(text => !keys.some(key => text.includes(key)))
      .filter(text => /\p{L}/u.test(text))
      .filter(text => ![...modelProse].some(prose => prose && text.includes(prose)));
    expect(stray).toEqual([]);
  });

  describe('the shape a screen reader and a narrow screen actually get', () => {
    it('labels itself with its OWN heading, not a hand-written id', () => {
      const { container } = render();
      const section = container.querySelector('section');
      const labelled = section?.getAttribute('aria-labelledby');

      expect(labelled).toBeTruthy();
      // A literal id collides the moment two of these render, and
      // `aria-labelledby` then points at the wrong heading.
      expect(labelled).not.toBe('relation-debrief-title');
      expect(container.querySelector(`#${CSS.escape(labelled!)}`)?.tagName).toBe('H3');
    });

    it('gives two mounted sections distinct ids', () => {
      const first = render().container.querySelector('section')?.getAttribute('aria-labelledby');
      const second = render().container.querySelector('section')?.getAttribute('aria-labelledby');
      expect(first).not.toBe(second);
    });

    it('makes each block a real heading, reachable by role', () => {
      render();
      expect(
        screen.getByRole('heading', { name: 'relations.debrief_open_points', level: 4 })
      ).toBeInTheDocument();
      expect(
        screen.getByRole('heading', { name: 'relations.debrief_notable_facts', level: 4 })
      ).toBeInTheDocument();
    });

    it('renders the points as a real list, never as typed bullets', () => {
      render();
      const items = screen.getAllByRole('listitem').map(node => node.textContent);
      expect(items).toContain('Répondre au devis');
      // A "•" typed into the text would be read out on top of the list
      // semantics the element already carries.
      expect(items.join('')).not.toContain('•');
    });

    it('keeps the switch OUT of the scan path — it follows the synthesis', () => {
      const { container } = render();
      const nodes = Array.from(container.querySelectorAll('h3, [role="switch"]'));
      // Title first, switch last: a setting is consulted, not scanned (ADR-208).
      expect(nodes[0]?.tagName).toBe('H3');
      expect(nodes.at(-1)?.getAttribute('role')).toBe('switch');
    });

    it('gives the refresh control a real touch target', () => {
      render();
      const button = screen.getByRole('button', { name: /relations\.debrief_rebuild/ });
      // 44px, the same as every other per-section refresh on this card.
      expect(button.className).toContain('min-h-11');
      expect(button.className).toContain('min-w-11');
    });

    it('offers the way back even when the feature is off', () => {
      render({ enabled: false });
      expect(screen.getByRole('switch', { name: /relations\.debrief_switch/ })).toBeInTheDocument();
    });
  });

  describe('what the synthesis cost', () => {
    it('shows tokens and cost beside the words they paid for', () => {
      render();
      const badge = screen.getByTitle(/common\.llm_usage\.tooltip/);
      expect(badge).toBeInTheDocument();
      expect(badge.textContent).toMatch(/1|801/);
    });

    it('shows them to an account that never opted into the chat token strip', () => {
      // Deliberate, and the reason this test exists: `tokens_display_enabled`
      // gates the chat's per-message debug strip, not the price of an artefact
      // LIA wrote. The dashboard's synthesis and hero card have always shown
      // their cost unconditionally; the debrief is the third such surface and
      // follows the same rule, so one figure is never read under two rules.
      render();
      expect(screen.getByTitle(/common\.llm_usage\.tooltip/)).toBeInTheDocument();
    });

    it('shows nothing when the row cannot say what it cost', () => {
      // A debrief written before this was recorded made NO claim about its
      // cost; rendering 0,00 € would invent one.
      render({ debrief: debrief({ usage: null }) });
      expect(screen.queryByTitle(/common\.llm_usage\.tooltip/)).not.toBeInTheDocument();
    });
  });

  it.each<DebriefStatus>(['absent', 'building', 'ready', 'failed', 'empty'])(
    'renders %s without crashing',
    status => {
      render({ debrief: debrief({ status, body: status === 'ready' ? debrief().body : null }) });
      expect(screen.getByRole('region', TITLE)).toBeInTheDocument();
    }
  );
});
