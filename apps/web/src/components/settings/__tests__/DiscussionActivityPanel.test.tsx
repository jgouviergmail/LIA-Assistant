import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import type { Language } from '@/i18n/settings';
import type { DiscussionActivity } from '@/types/proactive-discussions';
import { DiscussionActivityPanel } from '../DiscussionActivityPanel';

function lookup(tree: unknown, path: string): unknown {
  return path
    .split('.')
    .reduce<unknown>(
      (node, part) =>
        node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined,
      tree
    );
}

/** A sentence template as a pattern: each {{placeholder}} matches any value. */
function sentence(template: string): RegExp {
  const parts = template.split(/{{\w+}}/).map(part => part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  return new RegExp(parts.join('.+'));
}

vi.mock('@/i18n/client', () => ({
  useTranslation: (lng: Language) => ({
    t: (key: string, values: Record<string, string | number> = {}) => {
      const tree = lng === 'fr' ? fr : en;
      // i18next's plural rule for these two languages: _one for 1, _other otherwise.
      const plural =
        values.count === undefined ? key : `${key}_${values.count === 1 ? 'one' : 'other'}`;
      const found = lookup(tree, key) ?? lookup(tree, plural);
      if (typeof found !== 'string') return key;
      return found.replace(/{{(\w+)}}/g, (_, name: string) => String(values[name] ?? ''));
    },
  }),
}));

type Run = NonNullable<DiscussionActivity['last_run']>;

const rebuild: Run = {
  kind: 'rebuild',
  state: 'completed',
  claimed_at: '2026-10-21T08:00:00Z',
  settled_at: '2026-10-21T08:01:00Z',
  reason: 'context_ready',
  stats: {
    pages: { ok: 3, empty: 1 },
    facts_read: 7,
    facts_admitted: 6,
    facts_offered: 5,
    facts_unclassified: 0,
    context_calls: 2,
    proposals: 4,
    proposals_refused: 0,
    research_refused: 0,
    context_updates: 2,
    items: 4,
  },
  usage: {
    tokens_in: 9000,
    tokens_out: 3000,
    tokens_cache: 0,
    google_requests: 1,
    cost_eur: 0.0317,
  },
};

// A later automatic run that updated the context and spoke: the page's figures are its own.
const opening: Run = {
  kind: 'opening',
  state: 'skipped',
  claimed_at: '2026-10-21T15:32:00Z',
  settled_at: '2026-10-21T15:33:00Z',
  reason: 'decision_skip',
  stats: { ...rebuild.stats!, facts_offered: 12, context_calls: 1, context_updates: 1, items: 19 },
  usage: {
    tokens_in: 1200,
    tokens_out: 300,
    tokens_cache: 100,
    google_requests: 1,
    cost_eur: 0.0042,
  },
};

const base: DiscussionActivity = {
  rebuild: 'idle',
  obstacle: null,
  last_rebuild: rebuild,
  last_update: opening,
  last_run: opening,
  budget: { configured: true, reached: null, resets_at: null },
  awaiting_reply: null,
};

// An opening published at 09:22 that holds the next one back until 10:22.
const awaiting = { since: '2026-10-23T09:22:29Z', until: '2026-10-23T10:22:29Z' };

/** An instant as the panel promises to write it: the reader's short date and time. */
function shown(value: string, lng: Language): string {
  return new Date(value).toLocaleString(lng === 'fr' ? 'fr-FR' : 'en-US', {
    dateStyle: 'short',
    timeStyle: 'short',
  });
}

/** The figure a definition list states under one label. */
function figure(label: string): string | null | undefined {
  return screen.getByText(label, { selector: 'dt' }).parentElement?.querySelector('dd')
    ?.textContent;
}

describe.each(['en', 'fr'] as const)('discussion activity in %s', lng => {
  const messages = (lng === 'fr' ? fr : en).discussions;

  it('dates the last rebuild and the last context update, each under its label', () => {
    render(<DiscussionActivityPanel lng={lng} activity={base} />);
    // The rebuild's outcome is a status badge beside its date.
    expect(figure(messages.activity.rebuilt_at)).toContain(messages.rebuild_states.completed);
    expect(figure(messages.activity.updated_at)).toMatch(/\d/);
  });

  it('titles the LAST run with its kind, and shows its own reason and cost', () => {
    render(<DiscussionActivityPanel lng={lng} activity={base} />);
    const section = screen.getByRole('region', { name: messages.activity.last_run });
    expect(
      within(section).getByRole('heading', { name: messages.activity.last_run })
    ).toBeVisible();
    expect(within(section).getByText(messages.run_kinds.opening)).toBeVisible();
    expect(within(section).getByText(messages.activity.reason.decision_skip)).toBeVisible();
    expect(screen.queryByText(messages.activity.reason.context_ready)).not.toBeInTheDocument();
    // Its own ledger row — never the rebuild's.
    expect(within(section).getByText(/0[,.]004200/)).toBeVisible();
    expect(screen.queryByText(/0[,.]031700/)).not.toBeInTheDocument();
    expect(within(section).getByText(/GOOGLE/)).toBeVisible();
  });

  it('states what the last run read and interpreted, one labelled figure each', () => {
    render(<DiscussionActivityPanel lng={lng} activity={base} />);
    const figures = messages.activity.figures;
    // Four pages (3 ok + 1 empty), then each count of the run.
    expect(figure(figures.pages)).toBe('4');
    expect(figure(figures.facts)).toBe('7');
    expect(figure(figures.admitted)).toBe('6');
    expect(figure(figures.offered)).toBe('12');
    expect(figure(figures.calls)).toBe('1');
    expect(figure(figures.items)).toBe('19');
  });

  it('writes each figure in the reader’s number format', () => {
    render(
      <DiscussionActivityPanel
        lng={lng}
        activity={{
          ...base,
          last_run: { ...opening, stats: { ...opening.stats!, facts_read: 1234 } },
        }}
      />
    );
    expect(figure(messages.activity.figures.facts)).toBe(lng === 'fr' ? '1 234' : '1,234');
  });

  it('dates the rebuild first, then the update, then the last run — each a machine-readable instant', () => {
    render(<DiscussionActivityPanel lng={lng} activity={base} />);
    const instants = Array.from(document.querySelectorAll('time')).map(node =>
      node.getAttribute('datetime')
    );
    // The rebuild is its own run; the update and the last run are one run here.
    expect(instants).toEqual([rebuild.settled_at, opening.settled_at, opening.settled_at]);
  });

  it('puts a ceiling that stops LIA before everything else', () => {
    render(
      <DiscussionActivityPanel
        lng={lng}
        activity={{
          ...base,
          budget: { configured: true, reached: 'owner_day', resets_at: '2026-10-22T00:00:00Z' },
        }}
      />
    );
    const status = screen.getByRole('status');
    const firstFact = screen.getByText(messages.activity.rebuilt_at, { selector: 'dt' });
    expect(status.compareDocumentPosition(firstFact) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING
    );
  });

  it('counts the proposals set aside, and says nothing when none was', () => {
    const { rerender } = render(
      <DiscussionActivityPanel
        lng={lng}
        activity={{
          ...base,
          last_run: { ...opening, stats: { ...opening.stats!, proposals_refused: 3 } },
        }}
      />
    );
    expect(
      screen.getByText(messages.activity.proposals_refused_other.replace('{{count}}', '3'))
    ).toBeVisible();
    rerender(<DiscussionActivityPanel lng={lng} activity={base} />);
    expect(
      screen.queryByText(sentence(messages.activity.proposals_refused_other))
    ).not.toBeInTheDocument();
  });

  it('writes no reason and no figures for a run that recorded none', () => {
    render(
      <DiscussionActivityPanel
        lng={lng}
        activity={{ ...base, last_run: { ...opening, reason: null, stats: null } }}
      />
    );
    expect(screen.queryByText(messages.activity.reason.decision_skip)).not.toBeInTheDocument();
    expect(screen.queryByText(messages.activity.figures.calls)).not.toBeInTheDocument();
  });

  it('shows no amount and no ceiling while none stops a run', () => {
    render(<DiscussionActivityPanel lng={lng} activity={base} />);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it.each([
    ['owner_day', '2026-10-22T00:00:00Z'],
    ['instance_day', '2026-10-22T00:00:00Z'],
    ['instance_budget', '2026-10-22T00:00:00Z'],
    ['usage_limit', null],
    ['run_ceiling', null],
  ] as const)('says plainly when the %s ceiling stops LIA', (reached, resets_at) => {
    render(
      <DiscussionActivityPanel
        lng={lng}
        activity={{ ...base, budget: { configured: true, reached, resets_at } }}
      />
    );
    const status = screen.getByRole('status');
    expect(status.textContent).toMatch(sentence(messages.ceiling[reached]));
    // A day ceiling names the day it renews; a quota or a run ceiling promises none.
    expect(/\d/.test(status.textContent ?? '')).toBe(resets_at !== null);
  });

  it('says an opening awaits a reply, since when and until when, before the dated facts', () => {
    render(<DiscussionActivityPanel lng={lng} activity={{ ...base, awaiting_reply: awaiting }} />);
    const notice = screen.getByRole('status');
    expect(notice.textContent).toBe(
      messages.activity.awaiting_reply
        .replace('{{since}}', shown(awaiting.since, lng))
        .replace('{{until}}', shown(awaiting.until, lng))
    );
    const firstFact = screen.getByText(messages.activity.rebuilt_at, { selector: 'dt' });
    expect(notice.compareDocumentPosition(firstFact) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING
    );
  });

  it('puts a ceiling that stops LIA before the reply an opening awaits', () => {
    render(
      <DiscussionActivityPanel
        lng={lng}
        activity={{
          ...base,
          budget: { configured: true, reached: 'owner_day', resets_at: '2026-10-24T00:00:00Z' },
          awaiting_reply: awaiting,
        }}
      />
    );
    const [first, second] = screen.getAllByRole('status');
    expect(first.textContent).toMatch(sentence(messages.ceiling.owner_day));
    expect(second.textContent).toMatch(sentence(messages.activity.awaiting_reply));
  });

  it('shows nothing before any run when no ceiling is reached', () => {
    const { container } = render(
      <DiscussionActivityPanel
        lng={lng}
        activity={{ ...base, last_rebuild: null, last_update: null, last_run: null }}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('shows nothing of a budget the operator never configured', () => {
    const { container } = render(
      <DiscussionActivityPanel
        lng={lng}
        activity={{
          ...base,
          last_rebuild: null,
          last_update: null,
          last_run: null,
          budget: { configured: false, reached: null, resets_at: null },
        }}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });
});
