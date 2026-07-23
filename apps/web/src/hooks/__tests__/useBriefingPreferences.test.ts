/**
 * Briefing grid preference helpers (UXR Lot 5, B4) — pure reorder/visibility
 * logic behind the keyboard buttons and the drag-and-drop enhancement.
 */

import { describe, it, expect } from 'vitest';

import { moveSection, reorderTo, toggleHidden } from '../useBriefingPreferences';
import type { BriefingSection } from '@/types/briefing';

const ORDER: BriefingSection[] = ['weather', 'agenda', 'mails'];

describe('moveSection — keyboard ↑/↓', () => {
  it('swaps one step in each direction', () => {
    expect(moveSection(ORDER, 'agenda', 'up')).toEqual(['agenda', 'weather', 'mails']);
    expect(moveSection(ORDER, 'agenda', 'down')).toEqual(['weather', 'mails', 'agenda']);
  });

  it('is identity at the edges and for unknown names', () => {
    expect(moveSection(ORDER, 'weather', 'up')).toBe(ORDER);
    expect(moveSection(ORDER, 'mails', 'down')).toBe(ORDER);
    expect(moveSection(ORDER, 'tasks', 'up')).toBe(ORDER);
  });

  it('never mutates its input', () => {
    moveSection(ORDER, 'agenda', 'up');
    expect(ORDER).toEqual(['weather', 'agenda', 'mails']);
  });
});

describe('reorderTo — drag-and-drop', () => {
  it('moves a section to the target index', () => {
    expect(reorderTo(ORDER, 'mails', 0)).toEqual(['mails', 'weather', 'agenda']);
    expect(reorderTo(ORDER, 'weather', 2)).toEqual(['agenda', 'mails', 'weather']);
  });

  it('is identity for no-ops and invalid targets', () => {
    expect(reorderTo(ORDER, 'weather', 0)).toBe(ORDER);
    expect(reorderTo(ORDER, 'weather', 9)).toBe(ORDER);
    expect(reorderTo(ORDER, 'tasks', 1)).toBe(ORDER);
  });
});

describe('toggleHidden', () => {
  it('adds and removes symmetrically', () => {
    expect(toggleHidden([], 'weather')).toEqual(['weather']);
    expect(toggleHidden(['weather'], 'weather')).toEqual([]);
    expect(toggleHidden(['weather'], 'agenda')).toEqual(['weather', 'agenda']);
  });
});
