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
