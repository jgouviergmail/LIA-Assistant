/**
 * PerformedEffects — the claim under the bubble (ADR-263).
 *
 * Oracles are visible state and accessible name: the block names itself, each
 * line reads in the READER's language (resolved here from `label_key` +
 * `values`, never shipped translated), a failure is stated rather than
 * coloured, and a turn that changed nothing renders nothing at all.
 *
 * Deliberately not a disclosure: a claim the reader must expand to see is a
 * claim they will miss, so there is no toggle to test — the content is either
 * present or absent.
 */

import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { PerformedEffects } from '@/components/chat/PerformedEffects';
import type { PerformedEffect } from '@/types/performed-effects';

// Interpolating translator: proves the wording is resolved client-side with
// the row's values, which is the whole point of shipping keys.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const dictionary: Record<string, string> = {
        'chat.effects.title': 'Actions performed',
        'chat.effects.failed': 'failed',
        'effects.labels.draft.email': 'Sent an email to {recipient}',
        'effects.labels.control_hue_light_tool': 'Changed the {target} light',
      };
      const wording = dictionary[key];
      if (wording === undefined) return (options?.defaultValue as string) ?? '';
      return wording.replace(/\{(\w+)\}/g, (_m, name) => String(options?.[name] ?? ''));
    },
  }),
}));

function effect(overrides: Partial<PerformedEffect> = {}): PerformedEffect {
  return {
    labelKey: 'effects.labels.draft.email',
    values: { recipient: 'Marie' },
    status: 'succeeded',
    toolName: 'draft:email',
    ...overrides,
  };
}

describe('PerformedEffects', () => {
  it('names itself and states what was done, in the reader s language', () => {
    render(<PerformedEffects effects={[effect()]} />);

    expect(screen.getByRole('region', { name: 'Actions performed' })).toBeInTheDocument();
    expect(screen.getByText('Sent an email to Marie')).toBeInTheDocument();
  });

  it('renders nothing for a turn that changed nothing', () => {
    const { container } = render(<PerformedEffects effects={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when no effect is given at all', () => {
    const { container } = render(<PerformedEffects />);
    expect(container).toBeEmptyDOMElement();
  });

  it('states a failure in words, not only in colour', () => {
    render(<PerformedEffects effects={[effect({ status: 'failed' })]} />);

    expect(screen.getByText('failed')).toBeInTheDocument();
  });

  it('lists every effect of the turn', () => {
    render(
      <PerformedEffects
        effects={[
          effect(),
          effect({
            labelKey: 'effects.labels.control_hue_light_tool',
            values: { target: 'Salon' },
            toolName: 'control_hue_light_tool',
          }),
        ]}
      />
    );

    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    expect(screen.getByText('Changed the Salon light')).toBeInTheDocument();
  });

  it('drops a line whose wording is unknown rather than printing a key', () => {
    render(<PerformedEffects effects={[effect({ labelKey: 'effects.labels.not_translated' })]} />);

    expect(screen.queryByText(/effects\.labels/)).not.toBeInTheDocument();
  });

  it('renders nothing when NO line can be worded', () => {
    const { container } = render(
      <PerformedEffects effects={[effect({ labelKey: 'effects.labels.not_translated' })]} />
    );

    expect(container).toBeEmptyDOMElement();
  });

  it('never exposes the tool name to a user', () => {
    render(<PerformedEffects effects={[effect()]} />);

    expect(screen.queryByText(/draft:email/)).not.toBeInTheDocument();
  });
});
