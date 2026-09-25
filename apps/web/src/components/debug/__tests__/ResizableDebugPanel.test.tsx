/**
 * ResizableDebugPanel — the person widens or narrows the debug panel by hand,
 * into the conversation (owner request 2026-09-24).
 *
 * The handle is a focusable window splitter: a drag moves it, the arrows move
 * it (Shift for larger steps), Home/End reach the bounds, Enter or a
 * double-click restores the default. The conversation keeps its floor, and
 * the chosen width is kept per device — clamped, never rewritten, when a
 * narrower window cannot hold it.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { DEBUG_PANEL_PREFS_KEY } from '@/lib/constants';
import { useDebugPanelStore } from '@/stores/debugPanelStore';

import { ResizableDebugPanel } from '../ResizableDebugPanel';
import {
  DEBUG_PANEL_CHAT_MIN_WIDTH,
  DEBUG_PANEL_GAP,
  DEBUG_PANEL_WIDTH_DEFAULT,
  DEBUG_PANEL_WIDTH_MIN,
  DEBUG_PANEL_WIDTH_STEP,
} from '../utils/constants';

/** The width jsdom cannot compute: the row holding the conversation and the panel. */
function layoutRow(width: number) {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
    width,
    height: 800,
    top: 0,
    left: 0,
    right: width,
    bottom: 800,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  } as DOMRect);
}

function renderPanel() {
  render(
    <div>
      <ResizableDebugPanel>
        <p>panel body</p>
      </ResizableDebugPanel>
    </div>
  );
  return screen.getByRole('separator', { name: 'chat.debug_panel.resize' });
}

const ROW = 1600;
const MAX = ROW - DEBUG_PANEL_CHAT_MIN_WIDTH - DEBUG_PANEL_GAP;

beforeEach(() => {
  localStorage.removeItem(DEBUG_PANEL_PREFS_KEY);
  useDebugPanelStore.getState().reset();
  layoutRow(ROW);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('ResizableDebugPanel', () => {
  it('starts at the default width, behind a handle a keyboard can reach', () => {
    const handle = renderPanel();

    expect(handle).toHaveAttribute('aria-orientation', 'vertical');
    expect(handle).toHaveAttribute('tabindex', '0');
    expect(handle).toHaveAttribute('aria-valuenow', String(DEBUG_PANEL_WIDTH_DEFAULT));
    expect(handle).toHaveAttribute('aria-valuemin', String(DEBUG_PANEL_WIDTH_MIN));
    expect(handle).toHaveAttribute('aria-valuemax', String(MAX));
    expect(screen.getByText('panel body')).toBeInTheDocument();
  });

  it('widens with ArrowLeft and narrows with ArrowRight, four times as far with Shift', () => {
    const handle = renderPanel();

    fireEvent.keyDown(handle, { key: 'ArrowLeft' });
    expect(handle).toHaveAttribute('aria-valuenow', String(DEBUG_PANEL_WIDTH_DEFAULT + DEBUG_PANEL_WIDTH_STEP));

    fireEvent.keyDown(handle, { key: 'ArrowRight', shiftKey: true });
    expect(handle).toHaveAttribute(
      'aria-valuenow',
      String(DEBUG_PANEL_WIDTH_DEFAULT + DEBUG_PANEL_WIDTH_STEP - 4 * DEBUG_PANEL_WIDTH_STEP)
    );
  });

  it('reaches the bounds with Home and End, and never passes them', () => {
    const handle = renderPanel();

    fireEvent.keyDown(handle, { key: 'End' });
    expect(handle).toHaveAttribute('aria-valuenow', String(MAX));
    fireEvent.keyDown(handle, { key: 'ArrowLeft' });
    expect(handle).toHaveAttribute('aria-valuenow', String(MAX));

    fireEvent.keyDown(handle, { key: 'Home' });
    expect(handle).toHaveAttribute('aria-valuenow', String(DEBUG_PANEL_WIDTH_MIN));
  });

  it('restores the default on Enter and on a double-click', () => {
    const handle = renderPanel();

    fireEvent.keyDown(handle, { key: 'End' });
    fireEvent.keyDown(handle, { key: 'Enter' });
    expect(handle).toHaveAttribute('aria-valuenow', String(DEBUG_PANEL_WIDTH_DEFAULT));

    fireEvent.keyDown(handle, { key: 'End' });
    fireEvent.doubleClick(handle);
    expect(handle).toHaveAttribute('aria-valuenow', String(DEBUG_PANEL_WIDTH_DEFAULT));
  });

  it('follows a drag: moving the handle left widens the panel into the conversation', () => {
    const handle = renderPanel();

    fireEvent.pointerDown(handle, { pointerId: 1, clientX: 1000 });
    fireEvent.pointerMove(handle, { pointerId: 1, clientX: 850 });
    fireEvent.pointerUp(handle, { pointerId: 1, clientX: 850 });

    expect(handle).toHaveAttribute('aria-valuenow', String(DEBUG_PANEL_WIDTH_DEFAULT + 150));
    // Kept for this device.
    const persisted = JSON.parse(localStorage.getItem(DEBUG_PANEL_PREFS_KEY) ?? '{}');
    expect(persisted.state).toEqual({ width: DEBUG_PANEL_WIDTH_DEFAULT + 150 });
  });

  it('ignores a pointer that moves without having pressed the handle', () => {
    const handle = renderPanel();

    fireEvent.pointerMove(handle, { pointerId: 1, clientX: 100 });

    expect(handle).toHaveAttribute('aria-valuenow', String(DEBUG_PANEL_WIDTH_DEFAULT));
  });

  it('clamps a chosen width a narrower window cannot hold — and keeps it as chosen', () => {
    useDebugPanelStore.getState().setWidth(1200);
    layoutRow(1000);

    const handle = renderPanel();

    expect(handle).toHaveAttribute(
      'aria-valuenow',
      String(1000 - DEBUG_PANEL_CHAT_MIN_WIDTH - DEBUG_PANEL_GAP)
    );
    expect(useDebugPanelStore.getState().width).toBe(1200);
  });
});
