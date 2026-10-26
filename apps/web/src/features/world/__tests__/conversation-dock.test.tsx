import { act, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useWorldConversationDock, returnWorldFocus } from '../useWorldConversationDock';
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
function Dock({ open = true, mounted = true }: { open?: boolean; mounted?: boolean }) {
  const ref = useWorldConversationDock(open);
  return mounted ? <div ref={ref} role="dialog" aria-label="Conversation" /> : null;
}
it('stays inside the visible phone viewport when the keyboard opens and releases geometry on close', () => {
  const viewport = Object.assign(new EventTarget(), {
    width: 390,
    height: 844,
    offsetTop: 0,
    offsetLeft: 0,
  });
  vi.stubGlobal('visualViewport', viewport);
  const view = render(<Dock />);
  const dock = screen.getByRole('dialog');
  expect(dock.style.width).toBe('374px');
  expect(dock.style.height).toBe('760px');
  act(() => {
    viewport.height = 320;
    viewport.offsetTop = 60;
    viewport.dispatchEvent(new Event('resize'));
  });
  expect(dock.style.top).toBe('68px');
  expect(dock.style.height).toBe('304px');
  view.rerender(<Dock open={false} />);
  expect(dock.style.height).toBe('');
  act(() => {
    viewport.dispatchEvent(new Event('resize'));
  });
  expect(dock.style.height).toBe('');
});

it('measures a dialog portal that attaches after its parent has opened', () => {
  const view = render(<Dock mounted={false} />);
  view.rerender(<Dock />);
  expect(screen.getByRole('dialog').style.height).not.toBe('');
});

it('returns to visible world controls when a responsive layout hides the original opener', () => {
  render(
    <section>
      <div className="world-prototype">
        <button className="world-hud-toggle">World controls</button>
      </div>
      <div className="world-session-strip">
        <button>Original opener</button>
      </div>
    </section>
  );
  const original = screen.getByRole('button', { name: 'Original opener' });
  // Browsers refuse to focus display:none controls after a viewport change.
  const focus = vi.spyOn(original, 'focus').mockImplementation(() => {});
  returnWorldFocus(new Event('close'), original);
  expect(focus).toHaveBeenCalledOnce();
  expect(screen.getByRole('button', { name: 'World controls' })).toHaveFocus();
});
