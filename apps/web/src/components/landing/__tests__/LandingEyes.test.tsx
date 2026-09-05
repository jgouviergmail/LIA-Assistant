/**
 * LandingEyes — the chat widget on the landing surface, at rest, lazily.
 *
 * `next/dynamic` is stubbed to a component that echoes its props: the point
 * of this test is the WIRING (surface, resting signals, client-only load),
 * the widget itself is tested in `components/eyes/__tests__`.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

// `vi.mock` is hoisted above every import and constant: the factory's
// state must be hoisted with it.
const hoisted = vi.hoisted(() => ({ dynamicOptions: [] as unknown[] }));

vi.mock('next/dynamic', () => ({
  default: (_loader: unknown, options: unknown) => {
    hoisted.dynamicOptions.push(options);
    return (props: Record<string, unknown>) => (
      <div
        data-testid="eyes-widget"
        data-surface={String(props.surface)}
        data-status={String(props.chatStatus)}
        data-phase={String(props.streamPhase)}
        data-hitl={String(props.hitlAwaiting)}
        data-style={String(props.styleId)}
      />
    );
  },
}));

import { LandingEyes } from '@/components/landing/LandingEyes';

describe('LandingEyes', () => {
  it('mounts the eyes widget on the LANDING surface, with every chat signal at rest', () => {
    render(<LandingEyes />);
    const widget = screen.getByTestId('eyes-widget');
    expect(widget).toHaveAttribute('data-surface', 'landing');
    expect(widget).toHaveAttribute('data-status', 'idle');
    expect(widget).toHaveAttribute('data-phase', 'answer');
    expect(widget).toHaveAttribute('data-hitl', 'false');
  });

  it('shows the CAPSULES to every visitor, whatever a chat user chose', () => {
    render(<LandingEyes />);
    expect(screen.getByTestId('eyes-widget')).toHaveAttribute('data-style', 'capsules');
  });

  it('loads the widget client-only — it positions itself from the viewport', () => {
    expect(hoisted.dynamicOptions).toContainEqual({ ssr: false });
  });
});
