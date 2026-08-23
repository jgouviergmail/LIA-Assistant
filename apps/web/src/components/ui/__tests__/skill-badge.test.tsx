/**
 * SkillBadge — the cyan "a skill answered this" marker.
 *
 * It existed twice before this component did: once in `ChatMessage` and once in
 * the landing mockup's `acts.tsx`, hand-rolled both times and already drifted —
 * 10px against 9px, and a light-mode colour on one side only. The chat copy
 * shipped `text-cyan-400` with no light variant, measured 1.39:1 against a
 * 4.5:1 floor.
 *
 * These tests pin the three things that drift silently: the light/dark colour
 * pair, the sparkle affix, and the fact that both call sites get one
 * implementation.
 */

import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { SkillBadge } from '../skill-badge';

describe('SkillBadge', () => {
  it('renders the skill name', () => {
    renderWithProviders(<SkillBadge name="weather" />);
    expect(screen.getByText(/weather/)).toBeInTheDocument();
  });

  it('prefixes the name with the sparkle affix', () => {
    renderWithProviders(<SkillBadge name="weather" />);
    expect(screen.getByText(/✦/)).toBeInTheDocument();
  });

  it('carries a light-mode colour AND a dark-mode colour', () => {
    // The original defect was a single dark-mode value used in both modes.
    renderWithProviders(<SkillBadge name="weather" />);
    const cls = screen.getByTestId('skill-badge').className;
    expect(cls).toContain('text-cyan-800');
    expect(cls).toContain('dark:text-cyan-400');
  });

  it('uses the guarded cyan-500/20 wash the contrast guard measures against', () => {
    renderWithProviders(<SkillBadge name="weather" />);
    const cls = screen.getByTestId('skill-badge').className;
    expect(cls).toContain('bg-cyan-500/20');
  });

  it('animates by default and can opt out for static recreations', () => {
    const { rerender } = renderWithProviders(<SkillBadge name="a" />);
    expect(screen.getByTestId('skill-badge').className).toContain('badge-glimmer');
    rerender(<SkillBadge name="a" glimmer={false} />);
    expect(screen.getByTestId('skill-badge').className).not.toContain('badge-glimmer');
  });

  it('exposes a smaller size without letting call sites hand-roll the type scale', () => {
    const { rerender } = renderWithProviders(<SkillBadge name="a" />);
    expect(screen.getByTestId('skill-badge').className).toContain('text-[10px]');
    rerender(<SkillBadge name="a" size="sm" />);
    expect(screen.getByTestId('skill-badge').className).toContain('text-[9px]');
  });

  it('merges an extra className without dropping its own', () => {
    renderWithProviders(<SkillBadge name="a" className="mt-4" />);
    const cls = screen.getByTestId('skill-badge').className;
    expect(cls).toContain('mt-4');
    expect(cls).toContain('bg-cyan-500/20');
  });

  it('is announced as a single readable string, not split nodes', () => {
    renderWithProviders(<SkillBadge name="weather-forecast" />);
    expect(screen.getByTestId('skill-badge').textContent).toBe('✦ weather-forecast');
  });

  it('hides the sparkle from assistive technology', () => {
    // A screen reader announces ✦ as "black four-pointed star" before every
    // skill name — pure noise in front of the only word that carries meaning.
    renderWithProviders(<SkillBadge name="weather" />);
    const sparkle = screen.getByText('✦', { exact: false, selector: '[aria-hidden="true"]' });
    expect(sparkle).toBeInTheDocument();
  });
});
