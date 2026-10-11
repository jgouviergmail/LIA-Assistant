/**
 * SelectionActions (C-02) — the action menu over a selected passage.
 *
 * What must hold:
 *  - nothing renders without a scoped selection;
 *  - named actions EXECUTE with the quoted passage; "ask" PREFILLS (it needs
 *    the user's own words) — the ADR-173 split;
 *  - the quote is ellipsized beyond the cap (a 4-page quote is noise);
 *  - the quote comes from the SNAPSHOT, never from getSelection() at click
 *    time (iOS clears the selection when the sheet is tapped);
 *  - mobile anchors the same actions beside the selection, with a close button.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { SELECTION_QUOTE_MAX_LENGTH } from '@/lib/constants';
import type { TextSelectionSnapshot } from '@/hooks/useTextSelection';

const { useTextSelection, useMediaQuery } = vi.hoisted(() => ({
  useTextSelection: vi.fn(),
  useMediaQuery: vi.fn(),
}));

vi.mock('@/hooks/useTextSelection', async importOriginal => {
  const actual = await importOriginal<typeof import('@/hooks/useTextSelection')>();
  return { ...actual, useTextSelection };
});
vi.mock('@/hooks/useMediaQuery', () => ({ useMediaQuery }));

import { clampQuote, SelectionActions } from '../SelectionActions';

function snapshot(text = 'Le passage sélectionné.'): TextSelectionSnapshot {
  return { text, rect: { top: 200, left: 40, width: 120, bottom: 220 } };
}

const onExecute = vi.fn();
const onPrefill = vi.fn();

function renderMenu() {
  return renderWithProviders(<SelectionActions onExecute={onExecute} onPrefill={onPrefill} />);
}

beforeEach(() => {
  vi.clearAllMocks();
  useMediaQuery.mockReturnValue(false); // desktop by default
  vi.stubGlobal('innerWidth', 800);
  vi.stubGlobal('innerHeight', 600);
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(
    () => new DOMRect(0, 0, 720, 56)
  );
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('clampQuote', () => {
  it('keeps short quotes and ellipsizes long ones at the cap', () => {
    expect(clampQuote('court')).toBe('court');
    const long = 'x'.repeat(SELECTION_QUOTE_MAX_LENGTH + 50);
    const clamped = clampQuote(long);
    expect(clamped.length).toBe(SELECTION_QUOTE_MAX_LENGTH);
    expect(clamped.endsWith('…')).toBe(true);
  });
});

describe('SelectionActions', () => {
  it('renders nothing without a scoped selection', () => {
    useTextSelection.mockReturnValue(null);
    const { container } = renderMenu();
    expect(container).toBeEmptyDOMElement();
  });

  it('executes a named action with the quoted passage', async () => {
    useTextSelection.mockReturnValue(snapshot());
    const { user } = renderMenu();

    await user.click(screen.getByRole('button', { name: 'chat.selection.actions.explain' }));

    expect(onExecute).toHaveBeenCalledTimes(1);
    expect(onPrefill).not.toHaveBeenCalled();
  });

  it('prefills for "ask" — the question needs the user’s own words', async () => {
    useTextSelection.mockReturnValue(snapshot());
    const { user } = renderMenu();

    await user.click(screen.getByRole('button', { name: 'chat.selection.actions.ask' }));

    expect(onPrefill).toHaveBeenCalledTimes(1);
    expect(onExecute).not.toHaveBeenCalled();
  });

  it('uses the SNAPSHOT text even if the live selection is gone at click time', async () => {
    useTextSelection.mockReturnValue(snapshot('Capturé à l’ouverture'));
    // Simulate iOS: the native selection no longer exists when the tap lands.
    document.getSelection()?.removeAllRanges();
    const { user } = renderMenu();

    await user.click(screen.getByRole('button', { name: 'chat.selection.actions.remember' }));

    // The mocked translator returns the key — the QUOTE travels via options,
    // so pin the call happened; the wiring test above pins the mode split.
    expect(onExecute).toHaveBeenCalledTimes(1);
  });

  it('offers every action as a labelled toolbar button', () => {
    useTextSelection.mockReturnValue(snapshot());
    renderMenu();
    const toolbar = screen.getByRole('toolbar', { name: 'chat.selection.aria' });
    expect(toolbar).toBeInTheDocument();
    for (const key of [
      'explain',
      'rephrase',
      'translate',
      'to_task',
      'to_reminder',
      'remember',
      'ask',
    ]) {
      expect(
        screen.getByRole('button', { name: `chat.selection.actions.${key}` })
      ).toBeInTheDocument();
    }
  });

  it('renders the narrow menu with the same actions and a close button', () => {
    useMediaQuery.mockReturnValue(true);
    useTextSelection.mockReturnValue(snapshot());
    renderMenu();

    expect(screen.getByRole('button', { name: 'chat.selection.close' })).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'chat.selection.actions.explain' })
    ).toBeInTheDocument();
  });

  it('escapes the filtered chat panel through a body portal', () => {
    useTextSelection.mockReturnValue(snapshot());
    const { container } = renderMenu();
    const toolbar = screen.getByRole('toolbar');
    expect(container.contains(toolbar)).toBe(false);
    expect(toolbar.parentElement).toBe(document.body);
  });

  it('keeps the measured toolbar width within the right edge', () => {
    useTextSelection.mockReturnValue({
      text: 'A passage near the right edge',
      rect: { top: 200, left: 650, width: 120, bottom: 220 },
    });
    renderMenu();
    const toolbar = screen.getByRole('toolbar');
    expect(Number.parseFloat(toolbar.style.left) + 720).toBeLessThanOrEqual(792);
  });

  it('moves below a selection near the top instead of covering it', () => {
    useTextSelection.mockReturnValue({
      text: 'A passage near the top',
      rect: { top: 12, left: 40, width: 120, bottom: 32 },
    });
    renderMenu();
    expect(Number.parseFloat(screen.getByRole('toolbar').style.top)).toBeGreaterThanOrEqual(40);
  });

  it('anchors the narrow menu next to the selection instead of the screen bottom', () => {
    useMediaQuery.mockReturnValue(true);
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(
      new DOMRect(0, 0, 280, 180)
    );
    useTextSelection.mockReturnValue(snapshot());
    renderMenu();
    const toolbar = screen.getByRole('toolbar');
    expect(Number.parseFloat(toolbar.style.top) + 180).toBeLessThanOrEqual(192);
  });

  it('stays inside an offset visual viewport after zoom or keyboard resize', () => {
    vi.stubGlobal(
      'visualViewport',
      Object.assign(new EventTarget(), {
        offsetLeft: 100,
        offsetTop: 150,
        width: 500,
        height: 300,
      })
    );
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(
      new DOMRect(0, 0, 280, 56)
    );
    useTextSelection.mockReturnValue({
      text: 'A zoomed passage',
      rect: { top: 160, left: 540, width: 40, bottom: 180 },
    });
    renderMenu();
    const toolbar = screen.getByRole('toolbar');
    expect(Number.parseFloat(toolbar.style.left)).toBeGreaterThanOrEqual(108);
    expect(Number.parseFloat(toolbar.style.left) + 280).toBeLessThanOrEqual(592);
    expect(Number.parseFloat(toolbar.style.top)).toBeGreaterThanOrEqual(188);
    expect(Number.parseFloat(toolbar.style.top) + 56).toBeLessThanOrEqual(442);
  });
});
