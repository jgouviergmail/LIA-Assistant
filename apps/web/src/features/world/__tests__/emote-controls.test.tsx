import { fireEvent, render, screen } from '@testing-library/react';
import { createRef } from 'react';
import { expect, it, vi } from 'vitest';
import { WorldEmoteControls } from '../WorldEmoteControls';
import userEvent from '@testing-library/user-event';
import { EMOTES } from '../emote-catalogue';

it('dispatches shortcuts only from the focused scene and ignores typing, repeats and disabled input', () => {
  const canvas = createRef<HTMLCanvasElement>();
  const send = vi.fn();
  const { rerender, unmount } = render(
    <>
      <canvas ref={canvas} tabIndex={0} aria-label="World scene" />
      <input aria-label="chat" />
      <WorldEmoteControls
        lng="fr"
        canvasRef={canvas}
        disabled={false}
        onSelect={send}
        onReturnFocus={() => {}}
      />
    </>
  );
  fireEvent.keyDown(screen.getByRole('textbox'), { code: 'Digit1' });
  expect(send).not.toHaveBeenCalled();
  canvas.current?.focus();
  fireEvent.keyDown(canvas.current!, { code: 'Digit1', repeat: true });
  fireEvent.keyDown(canvas.current!, { code: 'Digit1', ctrlKey: true });
  expect(send).not.toHaveBeenCalled();
  fireEvent.keyDown(canvas.current!, { code: 'Digit1' });
  expect(send).toHaveBeenCalledExactlyOnceWith('wave');
  rerender(
    <>
      <canvas ref={canvas} tabIndex={0} aria-label="World scene" />
      <WorldEmoteControls
        lng="fr"
        canvasRef={canvas}
        disabled
        onSelect={send}
        onReturnFocus={() => {}}
      />
    </>
  );
  canvas.current?.focus();
  fireEvent.keyDown(canvas.current!, { code: 'Digit2' });
  expect(send).toHaveBeenCalledTimes(1);
  unmount();
  fireEvent.keyDown(document, { code: 'Digit2' });
  expect(send).toHaveBeenCalledTimes(1);
});

it('offers all six native menu actions, returns focus after selection and keeps Escape on the trigger', async () => {
  const user = userEvent.setup();
  const canvas = createRef<HTMLCanvasElement>();
  const select = vi.fn();
  const focus = vi.fn(() => canvas.current?.focus());
  render(
    <>
      <canvas ref={canvas} tabIndex={0} aria-label="World scene" />
      <WorldEmoteControls
        lng="fr"
        canvasRef={canvas}
        disabled={false}
        onSelect={select}
        onReturnFocus={focus}
      />
    </>
  );
  const trigger = screen.getByRole('button');
  await user.click(trigger);
  expect(screen.getAllByRole('menuitem')).toHaveLength(6);
  await user.click(screen.getAllByRole('menuitem')[0]);
  expect(select).toHaveBeenCalledExactlyOnceWith('wave');
  expect(focus).toHaveBeenCalledOnce();
  expect(canvas.current).toHaveFocus();
  await user.click(trigger);
  await user.keyboard('{Escape}');
  expect(trigger).toHaveFocus();
  expect(focus).toHaveBeenCalledOnce();
});

it('offers all six direct gestures without a menu and returns control to the scene after a tap', async () => {
  const user = userEvent.setup();
  const canvas = createRef<HTMLCanvasElement>();
  const select = vi.fn();
  const focus = vi.fn(() => canvas.current?.focus());
  render(
    <>
      <canvas ref={canvas} tabIndex={0} aria-label="World scene" />
      <WorldEmoteControls
        lng="fr"
        canvasRef={canvas}
        disabled={false}
        presentation="direct"
        onSelect={select}
        onReturnFocus={focus}
      />
    </>
  );
  const buttons = screen.getAllByRole('button');
  expect(buttons).toHaveLength(6);
  expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  for (const [index, button] of buttons.entries()) {
    expect(button).toHaveAccessibleName();
    expect(button).toHaveAttribute('aria-keyshortcuts', String(index + 1));
    await user.click(button);
    expect(select).toHaveBeenLastCalledWith(EMOTES[index]);
    expect(canvas.current).toHaveFocus();
  }
  expect(select).toHaveBeenCalledTimes(6);
  expect(focus).toHaveBeenCalledTimes(6);
});

it('keeps one shortcut owner through presentation changes and refuses paused or hidden direct gestures', async () => {
  const user = userEvent.setup();
  const canvas = createRef<HTMLCanvasElement>();
  const select = vi.fn();
  const controls = (presentation: 'menu' | 'direct', disabled = false) => (
    <>
      <canvas ref={canvas} tabIndex={0} aria-label="World scene" />
      <WorldEmoteControls
        lng="fr"
        canvasRef={canvas}
        disabled={disabled}
        presentation={presentation}
        onSelect={select}
        onReturnFocus={() => canvas.current?.focus()}
      />
    </>
  );
  const { rerender, unmount } = render(controls('direct'));
  for (const presentation of ['menu', 'direct', 'menu', 'direct'] as const) {
    rerender(controls(presentation));
    canvas.current?.focus();
    fireEvent.keyDown(canvas.current!, { code: 'Digit1' });
  }
  expect(select).toHaveBeenCalledTimes(4);
  const focused = screen.getAllByRole('button')[2];
  focused.focus();
  rerender(controls('direct', true));
  // A pause keeps the focused gesture focusable and refuses it through its guard.
  expect(focused).toHaveFocus();
  for (const button of screen.getAllByRole('button')) {
    expect(button).not.toBeDisabled();
    expect(button).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(button);
  }
  expect(select).toHaveBeenCalledTimes(4);
  expect(focused).toHaveFocus();
  rerender(controls('direct'));
  const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
  await user.click(screen.getAllByRole('button')[0]);
  expect(select).toHaveBeenCalledTimes(4);
  hidden.mockRestore();
  unmount();
  fireEvent.keyDown(document, { code: 'Digit1' });
  expect(select).toHaveBeenCalledTimes(4);
});

it('keeps the paused menu trigger focused, never opens it, and closes an open menu for good', async () => {
  const user = userEvent.setup();
  const canvas = createRef<HTMLCanvasElement>();
  const select = vi.fn();
  const controls = (disabled: boolean) => (
    <>
      <canvas ref={canvas} tabIndex={0} aria-label="World scene" />
      <WorldEmoteControls
        lng="fr"
        canvasRef={canvas}
        disabled={disabled}
        onSelect={select}
        onReturnFocus={() => canvas.current?.focus()}
      />
    </>
  );
  const { rerender } = render(controls(false));
  const trigger = screen.getByRole('button', { name: 'world.emotes.title' });
  await user.click(trigger);
  expect(screen.getAllByRole('menuitem')).toHaveLength(6);
  rerender(controls(true));
  expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  rerender(controls(false));
  expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  trigger.focus();
  rerender(controls(true));
  expect(trigger).toHaveFocus();
  expect(trigger).not.toBeDisabled();
  expect(trigger).toHaveAttribute('aria-disabled', 'true');
  await user.click(trigger);
  await user.keyboard('{Enter}');
  expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  expect(select).not.toHaveBeenCalled();
  rerender(controls(false));
  await user.click(trigger);
  expect(screen.getAllByRole('menuitem')).toHaveLength(6);
});
