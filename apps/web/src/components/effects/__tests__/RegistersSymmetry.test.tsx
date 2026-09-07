/**
 * The two registers must READ the same (ADR-263, owner ask 2026-09-05).
 *
 * They hold different things — one row per action, one per consultation — but
 * they are two tabs of one page, and a reader switching between them must not
 * find the controls somewhere else. Reported live: « les boutons n'apparaissent
 * pas aux mêmes endroits ».
 *
 * Two causes, both structural rather than cosmetic:
 *
 * 1. the header laid the title and the actions out with `justify-between` and
 *    `flex-wrap`, so where the buttons landed depended on how long the title
 *    was — and the two titles differ in length, in six languages;
 * 2. the action register always showed its status filter while the
 *    consultation register showed its capability filter only above one
 *    capability, so the list below started at two different heights.
 *
 * The oracle is the rendered DOM of both, compared. A snapshot would freeze the
 * markup; this compares the two against EACH OTHER, which is the actual
 * requirement and survives a redesign that changes both.
 */

import { describe, expect, it, vi } from 'vitest';
import { render, type RenderResult } from '@testing-library/react';

import { EffectsJournal } from '@/components/effects/EffectsJournal';
import { TreatmentsJournal } from '@/components/effects/TreatmentsJournal';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    // Deliberately DIFFERENT lengths: the defect was a layout that depended on
    // them, so a stub returning one word everywhere would hide it.
    t: (key: string) =>
      key.endsWith('.title')
        ? key.includes('treatments')
          ? 'Journal des consultations que LIA a faites'
          : 'Actions'
        : key,
    i18n: { language: 'fr' },
  }),
}));

const effectEntry = {
  id: 'effect-1',
  tool_name: 'send_email_tool',
  status: 'succeeded',
  label_key: 'effects.label.email_sent',
  label_values: {},
  mutation_policy: 'draft',
  source: 'user',
  execution_mode: 'pipeline',
  thread_id: 'thread-A',
  run_id: 'run-1',
  claimed_at: '2026-09-05T10:00:00Z',
  closed_at: '2026-09-05T10:00:01Z',
};

const treatmentEntry = {
  id: 'treatment-1',
  domain: 'email',
  tool_name: 'get_emails_tool',
  mutation_policy: 'read',
  outcome: 'ok',
  source: 'user',
  execution_mode: 'pipeline',
  duration_ms: 12,
  thread_id: 'thread-A',
  run_id: 'run-1',
  occurred_at: '2026-09-05T10:00:00Z',
};

const journalState = (entries: unknown[]) => ({
  entries,
  total: entries.length,
  hasMore: false,
  firstLoad: false,
  loading: false,
  error: null,
  loadMore: vi.fn(),
  refetch: vi.fn(),
});

vi.mock('@/hooks/useRegisterJournal', async importOriginal => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, useRegisterJournal: () => journalState([effectEntry]) };
});

vi.mock('@/hooks/useTreatmentsJournal', () => ({
  TREATMENTS_PAGE_SIZE: 20,
  useTreatmentsJournal: () => journalState([treatmentEntry]),
}));

vi.mock('@/components/effects/RegisterExportButton', () => ({
  RegisterExportButton: ({ register }: { register: string }) => (
    <div data-testid={`export-${register}`} />
  ),
}));

/** The shape a reader perceives: which landmarks exist, in which order. */
function skeletonOf(view: RenderResult): string[] {
  const header = view.container.querySelector('header');
  const groups = [...view.container.querySelectorAll('[role="group"]')];
  return [
    header ? `header:${header.className}` : 'header:MISSING',
    ...groups.map(group => `group:${group.className}`),
  ];
}

describe('The two registers read the same', () => {
  it('lays their headers out identically whatever the title length', () => {
    const actions = render(<EffectsJournal lng="fr" />);
    const consultations = render(<TreatmentsJournal lng="fr" />);

    const actionsHeader = actions.container.querySelector('header')?.className;
    const consultationsHeader = consultations.container.querySelector('header')?.className;

    expect(actionsHeader).toBe(consultationsHeader);
  });

  it('places the toolbar where the title cannot move it', () => {
    // `justify-between` with a wrapping title put the buttons on a different
    // line depending on the words above them.
    const view = render(<EffectsJournal lng="fr" />);
    const header = view.container.querySelector('header');

    expect(header?.className).toContain('flex-col');
    expect(header?.className).toContain('sm:flex-row');
  });

  it('gives both registers the same landmarks in the same order', () => {
    const actions = render(<EffectsJournal lng="fr" />);
    const consultations = render(<TreatmentsJournal lng="fr" />);

    expect(skeletonOf(actions)).toEqual(skeletonOf(consultations));
  });

  it('offers a filter on both, not on one', () => {
    const actions = render(<EffectsJournal lng="fr" />);
    const consultations = render(<TreatmentsJournal lng="fr" />);

    expect(actions.container.querySelectorAll('[role="group"]')).toHaveLength(
      consultations.container.querySelectorAll('[role="group"]').length
    );
  });
});

/** What one row shows a reader: its structure, stripped of the words. */
function rowShapeOf(view: RenderResult): string[] {
  const row = view.container.querySelector('li');
  if (!row) return ['row:MISSING'];
  return [
    `row:${row.className}`,
    ...[...row.querySelectorAll('*')].map(node => `${node.tagName}:${node.className}`),
  ];
}

describe('The three readings present the same information', () => {
  /**
   * Reported live, 2026-09-07: « l'écart de formatage entre les action,
   * consultation et à l'initiative de LIA : les affichages doivent être
   * homogène et présenter les mêmes informations ».
   *
   * The cause was two nearly identical row renderers: the action row showed
   * neither the capability nor the duration the consultation row showed. They
   * are ONE component now, but each journal still chooses what to hand it —
   * so a journal that stops passing a field diverges again, and that is what
   * these compare.
   */

  it('renders both registers rows with the same structure', () => {
    const actions = render(<EffectsJournal lng="fr" />);
    const consultations = render(<TreatmentsJournal lng="fr" />);

    expect(rowShapeOf(actions)).toEqual(rowShapeOf(consultations));
  });

  it('shows the capability on both, not on one', () => {
    const actions = render(<EffectsJournal lng="fr" />);
    const consultations = render(<TreatmentsJournal lng="fr" />);

    expect(actions.container.querySelector('.font-mono')?.textContent).toBe('send_email_tool');
    expect(consultations.container.querySelector('.font-mono')?.textContent).toBe(
      'get_emails_tool'
    );
  });

  it('carries a timestamp on every row of both', () => {
    const actions = render(<EffectsJournal lng="fr" />);
    const consultations = render(<TreatmentsJournal lng="fr" />);

    expect(actions.container.querySelector('time')).not.toBeNull();
    expect(consultations.container.querySelector('time')).not.toBeNull();
  });

  it('names the authorship on both', () => {
    const actions = render(<EffectsJournal lng="fr" />);
    const consultations = render(<TreatmentsJournal lng="fr" />);

    expect(actions.container.textContent).toContain('effects.journal.source.user');
    expect(consultations.container.textContent).toContain('effects.journal.source.user');
  });

  it('lets a long row reflow instead of overflowing on a phone', () => {
    // The detail line now carries one more badge on every consultation. It is
    // the same line in both registers, so the reflow rule is asserted once —
    // and `break-words` on the capability is what keeps a long MCP tool name
    // from pushing the row past the viewport.
    const view = render(<TreatmentsJournal lng="fr" />);
    const detail = view.container.querySelector('.font-mono')?.parentElement;

    expect(detail?.className).toContain('flex-wrap');
    expect(view.container.querySelector('.font-mono')?.className).toContain('break-words');
    expect(view.container.querySelector('.font-mono')?.className).toContain('min-w-0');
  });

  it('states the outcome in TEXT, since the glyph is hidden from assistive tech', () => {
    // `RegisterRow`'s icon is `aria-hidden`, so before the badge became
    // unconditional a successful consultation had NO accessible statement of
    // its outcome — only a colour a screen reader never sees.
    const consultations = render(<TreatmentsJournal lng="fr" />);

    expect(consultations.container.textContent).toContain('treatments.journal.outcome.ok');
  });

  it('reads the initiative tab through the very same row', () => {
    // The third reading is not a third renderer: it stacks the two registers
    // filtered to `initiative`. A separate row component there is how the
    // divergence came back the first time.
    const initiative = render(<EffectsJournal lng="fr" origin="initiative" />);
    const mine = render(<EffectsJournal lng="fr" origin="mine" />);

    expect(rowShapeOf(initiative)).toEqual(rowShapeOf(mine));
  });
});
