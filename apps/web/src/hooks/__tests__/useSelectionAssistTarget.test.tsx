import { act, fireEvent, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createSelectionStore } from '@/lib/selection-assist/store';
import { useSelectionAssistTarget } from '../useSelectionAssistTarget';

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  vi.useRealTimers();
  document.body.replaceChildren();
});
function setup() {
  const input = document.createElement('textarea');
  input.value = 'abc abc';
  document.body.append(input);
  input.focus();
  const store = createSelectionStore();
  const view = renderHook(({ enabled }) => useSelectionAssistTarget(store, enabled), {
    initialProps: { enabled: true },
  });
  const select = (start = 0, end = 3) =>
    act(() => {
      input.setSelectionRange(start, end);
      fireEvent.select(input);
      vi.advanceTimersByTime(200);
    });
  return { ...view, input, store, select };
}
describe('shared selection lifetime', () => {
  it.each(['touchEnd', 'touchCancel'] as const)(
    'waits for all native touches and reopens a dismissed selection after %s',
    event => {
      const { input, store, select } = setup();
      select();
      act(() => store.dismiss());
      act(() => fireEvent.touchStart(input, { touches: [{ identifier: 1 }, { identifier: 2 }] }));
      select();
      act(() => {
        fireEvent[event](input, { touches: [{ identifier: 2 }] });
        vi.advanceTimersByTime(1000);
      });
      expect(store.getSnapshot()).toBeNull();
      act(() => {
        fireEvent[event](input, { touches: [] });
        vi.advanceTimersByTime(200);
      });
      expect(store.getSnapshot()?.text).toBe('abc');
    }
  );
  it('recovers a native touch selection when WebKit omits the pointer release', () => {
    const { input, store, select } = setup();
    act(() => {
      fireEvent.pointerDown(input, { pointerId: 4, pointerType: 'touch' });
      fireEvent.touchStart(input, { touches: [{ identifier: 40 }] });
    });
    select();
    act(() => vi.advanceTimersByTime(1000));
    expect(store.getSnapshot()).toBeNull();
    act(() => {
      fireEvent.touchEnd(input, { touches: [] });
      vi.advanceTimersByTime(200);
    });
    expect(store.getSnapshot()).toMatchObject({ mode: 'edit', text: 'abc' });
  });
  it('waits for touch release after the browser cancels its pointer stream', () => {
    const { input, store, select } = setup();
    act(() => {
      fireEvent.pointerDown(input, { pointerId: 4, pointerType: 'touch' });
      fireEvent.touchStart(input, { touches: [{ identifier: 40 }] });
      fireEvent.pointerCancel(input, { pointerId: 4, pointerType: 'touch' });
    });
    select();
    act(() => vi.advanceTimersByTime(1000));
    expect(store.getSnapshot()).toBeNull();
    act(() => {
      fireEvent.touchEnd(input, { touches: [] });
      vi.advanceTimersByTime(200);
    });
    expect(store.getSnapshot()).toMatchObject({ mode: 'edit', text: 'abc' });
  });
  it('observes selection changes emitted on the field without bubbling', () => {
    const { input, store } = setup();
    act(() => vi.advanceTimersByTime(200));
    vi.spyOn(input, 'selectionStart', 'get').mockReturnValue(1);
    vi.spyOn(input, 'selectionEnd', 'get').mockReturnValue(3);
    act(() => {
      fireEvent(input, new Event('selectionchange', { bubbles: false }));
      vi.advanceTimersByTime(200);
    });
    expect(store.getSnapshot()).toMatchObject({ text: 'bc' });
  });
  it('never treats a touch release as the end of a held mouse selection', () => {
    const { input, store, select } = setup();
    act(() => fireEvent.pointerDown(input, { pointerId: 1, pointerType: 'mouse' }));
    select();
    act(() => {
      fireEvent.touchEnd(input, { touches: [] });
      vi.advanceTimersByTime(1000);
    });
    expect(store.getSnapshot()).toBeNull();
    act(() => {
      fireEvent.pointerUp(input, { pointerId: 1, pointerType: 'mouse' });
      vi.advanceTimersByTime(200);
    });
    expect(store.getSnapshot()?.text).toBe('abc');
  });
  it('keeps the editing session when an internal form hands focus to its response controls', async () => {
    const { store, select } = setup();
    select();
    const current = store.getSnapshot();
    const panel = document.createElement('div');
    panel.dataset.selectionAssistUi = '';
    const submit = document.createElement('button');
    const close = document.createElement('button');
    panel.append(submit, close);
    document.body.append(panel);
    act(() => submit.focus());
    await act(async () => {
      // Removing the submitted form can blur its focused button before layout
      // gives focus to the response's surviving close control.
      fireEvent.focusOut(submit, { relatedTarget: null });
      submit.remove();
      close.focus();
      await Promise.resolve();
    });
    expect(store.getSnapshot()).toBe(current);
    await act(async () => {
      close.blur();
      await Promise.resolve();
    });
    expect(store.getSnapshot()).toBeNull();
    expect(store.shouldRestoreFocus()).toBe(false);
  });
  it('immediately retires an editing target when keyboard focus moves to another field', () => {
    const { input, store, select } = setup();
    select();
    const other = document.createElement('textarea');
    document.body.append(other);
    act(() => other.focus());
    expect(store.getSnapshot()).toBeNull();
    act(() => vi.advanceTimersByTime(200));
    expect(store.getSnapshot()).toBeNull();
    expect(store.getSnapshot()?.element).not.toBe(input);
  });
  it('retires an editor when focus leaves for a non-editing control, but keeps its own controls', () => {
    const { input, store, select } = setup();
    select();
    const toolbar = document.createElement('div');
    toolbar.dataset.selectionAssistUi = '';
    const action = document.createElement('button');
    toolbar.append(action);
    const outside = document.createElement('button');
    document.body.append(toolbar, outside);
    const current = store.getSnapshot();
    act(() => action.focus());
    expect(store.getSnapshot()).toBe(current);
    act(() => outside.focus());
    expect(store.getSnapshot()).toBeNull();
    act(() => vi.advanceTimersByTime(200));
    expect(store.getSnapshot()).toBeNull();
    expect(document.activeElement).toBe(outside);
    expect(document.activeElement).not.toBe(input);
  });
  it('admits a different native selection after dismissal without requiring a pointer event', () => {
    const { store, select } = setup();
    select(0, 3);
    act(() => store.dismiss());
    select(0, 3);
    expect(store.getSnapshot()).toBeNull();
    // Native selection handles and accessibility tools may emit select alone.
    select(4, 7);
    expect(store.getSnapshot()).toMatchObject({ text: 'abc', start: 4, end: 7 });
  });
  it('keeps a caret closed through focus, selectionchange and pointer gestures', () => {
    const { store, input } = setup();
    act(() => {
      input.setSelectionRange(0, 0);
      fireEvent.focusIn(input);
      vi.advanceTimersByTime(200);
    });
    expect(store.getSnapshot()).toBeNull();
    act(() => {
      store.dismiss();
      fireEvent.focusIn(input);
      fireEvent(document, new Event('selectionchange'));
      vi.advanceTimersByTime(200);
    });
    expect(store.getSnapshot()).toBeNull();
    act(() => {
      fireEvent.pointerDown(input, { pointerId: 9 });
      fireEvent.pointerUp(input, { pointerId: 9 });
      vi.advanceTimersByTime(200);
    });
    expect(store.getSnapshot()).toBeNull();
  });
  it('keeps an empty field and typing at its caret free of contextual menus', () => {
    const { store, input } = setup();
    act(() => {
      input.value = '';
      input.setSelectionRange(0, 0);
      fireEvent.focusIn(input);
      vi.advanceTimersByTime(200);
    });
    expect(store.getSnapshot()).toBeNull();
    act(() => {
      fireEvent.input(input, { target: { value: 'Typing' } });
      input.setSelectionRange(6, 6);
      fireEvent.keyUp(input, { key: 'g' });
      vi.advanceTimersByTime(200);
    });
    expect(store.getSnapshot()).toBeNull();
  });
  it.each([false, true])(
    'window blur closes editing but preserves reading (readonly=%s)',
    readOnly => {
      const { input, store, select } = setup();
      input.readOnly = readOnly;
      select();
      const target = store.getSnapshot();
      expect(target?.text).toBe('abc');
      act(() => fireEvent(window, new Event('blur')));
      expect(store.getSnapshot()).toBe(readOnly ? target : null);
    }
  );
  it('waits for pointer release even when a person pauses during selection', () => {
    const { input, store, select } = setup();
    act(() => fireEvent.pointerDown(input, { pointerId: 1 }));
    select();
    act(() => vi.advanceTimersByTime(1000));
    expect(store.getSnapshot()).toBeNull();
    act(() => {
      fireEvent.pointerUp(input, { pointerId: 1 });
      vi.advanceTimersByTime(200);
    });
    expect(store.getSnapshot()?.text).toBe('abc');
  });
  it('waits until Shift is released during a paused keyboard selection', () => {
    const { input, store } = setup();
    act(() => {
      fireEvent.keyDown(input, { key: 'Shift', shiftKey: true });
      input.setSelectionRange(0, 3);
      fireEvent(document, new Event('selectionchange'));
      vi.advanceTimersByTime(1000);
    });
    expect(store.getSnapshot()).toBeNull();
    act(() => {
      fireEvent.keyUp(input, { key: 'Shift', shiftKey: false });
      vi.advanceTimersByTime(200);
    });
    expect(store.getSnapshot()?.text).toBe('abc');
  });
  it('a cancelled pointer gesture does not open a menu on its abandoned selection', () => {
    const { input, store, select } = setup();
    act(() => fireEvent.pointerDown(input, { pointerId: 1 }));
    select();
    act(() => {
      fireEvent.pointerCancel(input, { pointerId: 1 });
      vi.advanceTimersByTime(1000);
    });
    expect(store.getSnapshot()).toBeNull();
    act(() => {
      fireEvent.pointerDown(input, { pointerId: 2 });
      fireEvent.pointerUp(input, { pointerId: 2 });
      vi.advanceTimersByTime(200);
    });
    expect(store.getSnapshot()?.text).toBe('abc');
  });
  it('recovers when focus leaves the window before the held pointer is released', () => {
    const { input, store, select } = setup();
    act(() => fireEvent.pointerDown(input, { pointerId: 1 }));
    select();
    act(() => fireEvent(window, new Event('blur')));
    expect(store.getSnapshot()).toBeNull();
    select(4, 7);
    expect(store.getSnapshot()).toMatchObject({ start: 4, end: 7 });
  });
  it('keeps the frozen source while composing a question inside its own bubble', () => {
    const { select, store } = setup();
    select();
    const frozen = store.getSnapshot();
    const bubble = document.createElement('div');
    bubble.dataset.selectionAssistUi = '';
    const question = document.createElement('textarea');
    bubble.append(question);
    document.body.append(bubble);
    question.focus();
    act(() => {
      fireEvent.compositionStart(question);
      fireEvent.input(question, { target: { value: '解释一下' } });
      vi.advanceTimersByTime(200);
    });
    expect(store.getSnapshot()).toBe(frozen);
    act(() => fireEvent.pointerCancel(question, { pointerId: 2 }));
    expect(store.getSnapshot()).toBe(frozen);
    act(() => {
      fireEvent.compositionEnd(question);
      fireEvent(document, new Event('selectionchange'));
      vi.advanceTimersByTime(200);
    });
    expect(store.getSnapshot()).toBe(frozen);
  });
  it('captures only enabled scopes and removes its listeners on unmount', () => {
    const { select, store, rerender, unmount } = setup();
    select();
    expect(store.getSnapshot()?.text).toBe('abc');
    rerender({ enabled: false });
    select();
    expect(store.getSnapshot()).toBeNull();
    unmount();
    select();
    expect(store.getSnapshot()).toBeNull();
  });
  it('does not retain a target while an IME composition is active', () => {
    const { input, select, store } = setup();
    select();
    act(() => fireEvent.compositionStart(input));
    select();
    expect(store.getSnapshot()).toBeNull();
    act(() => {
      fireEvent.compositionEnd(input);
      vi.advanceTimersByTime(200);
    });
    expect(store.getSnapshot()?.text).toBe('abc');
  });
  it('Alt+Enter reaches the menu without replacing the selected target', () => {
    const { select, store } = setup();
    select();
    const target = store.getSnapshot();
    const toolbar = document.createElement('div');
    toolbar.dataset.selectionAssistUi = '';
    toolbar.setAttribute('role', 'toolbar');
    const button = document.createElement('button');
    toolbar.append(button);
    document.body.append(toolbar);
    act(() => fireEvent.keyDown(document, { key: 'Enter', altKey: true }));
    expect(button).toHaveFocus();
    act(() => {
      fireEvent(document, new Event('selectionchange'));
      vi.advanceTimersByTime(200);
    });
    expect(store.getSnapshot()).toBe(target);
  });
  it('a pointer outside abandons the old target before a new selection', () => {
    const { select, store, input } = setup();
    select();
    act(() => fireEvent.pointerDown(input));
    expect(store.getSnapshot()).toBeNull();
    act(() => fireEvent.pointerUp(input));
    select(4, 7);
    expect(store.getSnapshot()).toMatchObject({ start: 4, end: 7 });
  });
  it('the same words at another offset are a new target, including keyboard selection', () => {
    const { select, store } = setup();
    select();
    const previous = store.getSnapshot();
    select(4, 7);
    expect(store.getSnapshot()).not.toBe(previous);
    expect(store.getSnapshot()).toMatchObject({ start: 4, end: 7 });
  });
});
