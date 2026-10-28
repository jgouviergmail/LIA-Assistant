import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createRef, type ComponentProps } from 'react';
import { beforeEach, expect, it, vi } from 'vitest';
import { WorldPrototype } from '../WorldPrototype';
import type { WorldSnapshot } from '../types';
import type { WorldRuntime } from '../runtime';
import type { EmoteOutcome } from '../emote-catalogue';
import { WORLD } from '../definition';

const media = vi.hoisted(() => ({ compact: true }));
const local = vi.hoisted(() => ({ outcome: 'accepted' as EmoteOutcome, gestures: [] as string[] }));
vi.mock('@/hooks/useMediaQuery', () => ({
  useMediaQuery: (query: string) => !query.includes('reduced-motion') && media.compact,
}));
vi.mock('../WorldPhotoControls', () => ({ WorldPhotoControls: () => null }));
vi.mock('../WorldHelp', () => ({ WorldHelp: () => null }));
vi.mock('../WorldObjectHint', () => ({ WorldObjectHint: () => null }));
vi.mock('../useWorldRuntime', () => ({
  useWorldRuntime: () => ({
    canvasRef: canvas,
    snapshot,
    failed: false,
    retry: vi.fn(),
    command: (action: (runtime: WorldRuntime) => void) => action(runtimeDouble()),
    focusScene: () => canvas.current?.focus(),
  }),
}));
vi.mock('../WorldHud', () => ({
  WorldHud: ({
    widgets,
    gestures,
    onExpand,
  }: ComponentProps<typeof import('../WorldHud').WorldHud>) => (
    <>
      <button onClick={onExpand}>Toggle controls</button>
      <div data-testid="expanded-controls">{widgets}</div>
      <div data-testid="bottom-controls">{gestures}</div>
    </>
  ),
}));

const canvas = createRef<HTMLCanvasElement>();
function runtimeDouble(): WorldRuntime {
  return {
    photoScene: () => null,
    emote: kind => {
      local.gestures.push(kind);
      return local.outcome;
    },
    setSeason: vi.fn(),
    input: {
      direction: () => ({ x: 0, y: 0 }),
      hold: vi.fn(),
      release: vi.fn(),
      clear: vi.fn(),
      dispose: vi.fn(),
    },
    interact: vi.fn(),
    zoom: vi.fn(),
    recenter: vi.fn(),
    explore: vi.fn(),
    callBip: vi.fn(),
    setReducedMotion: vi.fn(),
    setQuality: vi.fn(),
    setPaused: vi.fn(),
    setHome: vi.fn(),
    setAtmosphere: vi.fn(),
    setRouteVisible: vi.fn(),
    setPrivateSignals: vi.fn(),
    setActingSource: vi.fn(),
    setConversationOpen: vi.fn(),
    snapshot: () => snapshot,
    destroy: vi.fn(),
  };
}
const snapshot: WorldSnapshot = {
  player: WORLD.spawn,
  bip: WORLD.bipSpawn,
  zone: 'arrival',
  zoom: 1,
  following: true,
  bipFollowing: false,
  metrics: { fps: 0, frameP95: 0, renderP95: 0, sprites: 0, textureBytes: 0 },
};
beforeEach(() => {
  media.compact = true;
  local.outcome = 'accepted';
  local.gestures = [];
});

it('moves the single gesture control between the folded bottom and expanded widgets', async () => {
  const user = userEvent.setup();
  const send = vi.fn(() => true);
  const expandedChange = vi.fn();
  render(
    <WorldPrototype
      lng="fr"
      ownerId="owner"
      connected
      onEmote={send}
      onHudExpandedChange={expandedChange}
    />
  );
  const bottom = within(screen.getByTestId('bottom-controls'));
  const expanded = within(screen.getByTestId('expanded-controls'));
  expect(bottom.getAllByRole('button')).toHaveLength(6);
  expect(expanded.queryByRole('button', { name: 'world.emotes.title' })).not.toBeInTheDocument();
  await user.click(bottom.getByRole('button', { name: 'world.emotes.wave' }));
  expect(send).toHaveBeenCalledExactlyOnceWith('wave');
  expect(canvas.current).toHaveFocus();
  await user.click(screen.getByRole('button', { name: 'Toggle controls' }));
  expect(expandedChange).toHaveBeenLastCalledWith(true);
  expect(bottom.queryByRole('button')).not.toBeInTheDocument();
  await user.click(expanded.getByRole('button', { name: 'world.emotes.title' }));
  await user.click(screen.getByRole('menuitem', { name: /world.emotes.thanks/ }));
  expect(send).toHaveBeenLastCalledWith('thanks');
  expect(expandedChange).toHaveBeenLastCalledWith(false);
  expect(bottom.getAllByRole('button')).toHaveLength(6);
  expect(canvas.current).toHaveFocus();
  canvas.current?.focus();
  fireEvent.keyDown(canvas.current!, { code: 'Digit3' });
  expect(send).toHaveBeenCalledTimes(3);
  expect(send).toHaveBeenLastCalledWith('applause');
});

it('preserves the desktop menu and disables folded actions while interaction is paused', () => {
  media.compact = false;
  const { rerender } = render(<WorldPrototype lng="fr" ownerId="owner" connected />);
  expect(screen.getByRole('button', { name: 'world.emotes.title' })).toBeEnabled();
  expect(
    within(screen.getByTestId('bottom-controls')).queryByRole('button')
  ).not.toBeInTheDocument();
  media.compact = true;
  rerender(<WorldPrototype lng="fr" ownerId="owner" connected interactionPaused />);
  const buttons = within(screen.getByTestId('bottom-controls')).getAllByRole('button');
  expect(buttons).toHaveLength(6);
  for (const button of buttons) expect(button).toHaveAttribute('aria-disabled', 'true');
});

it('follows parent HUD changes and requests controlled toggles without changing local presentation', async () => {
  const user = userEvent.setup();
  const expandedChange = vi.fn();
  const props = { lng: 'fr' as const, ownerId: 'owner', onHudExpandedChange: expandedChange };
  const { rerender } = render(<WorldPrototype {...props} hudExpanded />);
  const scene = screen.getByRole('region', { name: 'world.title' });
  const bottom = within(screen.getByTestId('bottom-controls'));
  const expanded = within(screen.getByTestId('expanded-controls'));
  expect(scene).toHaveAttribute('data-hud-expanded', 'true');
  expect(bottom.queryByRole('button')).not.toBeInTheDocument();
  expect(expanded.getByRole('button', { name: 'world.emotes.title' })).toBeEnabled();

  rerender(<WorldPrototype {...props} hudExpanded={false} />);
  expect(scene).toHaveAttribute('data-hud-expanded', 'false');
  expect(bottom.getAllByRole('button')).toHaveLength(6);
  expect(expanded.queryByRole('button', { name: 'world.emotes.title' })).not.toBeInTheDocument();
  expect(expandedChange).not.toHaveBeenCalled();

  await user.click(screen.getByRole('button', { name: 'Toggle controls' }));
  expect(expandedChange).toHaveBeenCalledExactlyOnceWith(true);
  expect(scene).toHaveAttribute('data-hud-expanded', 'false');
  rerender(<WorldPrototype {...props} hudExpanded />);
  expect(scene).toHaveAttribute('data-hud-expanded', 'true');
  expect(bottom.queryByRole('button')).not.toBeInTheDocument();
});

it('says a refused private gesture and keeps the touch controls where they were', async () => {
  const user = userEvent.setup();
  const expandedChange = vi.fn();
  local.outcome = 'rate_limited';
  render(
    <WorldPrototype lng="fr" ownerId="owner" hudExpanded onHudExpandedChange={expandedChange} />
  );
  const expanded = within(screen.getByTestId('expanded-controls'));
  await user.click(expanded.getByRole('button', { name: 'world.emotes.title' }));
  await user.click(screen.getByRole('menuitem', { name: /world.emotes.wave/ }));
  expect(local.gestures).toEqual(['wave']);
  expect(screen.getByRole('status')).toHaveTextContent('world.emotes.rate_limited');
  expect(expandedChange).not.toHaveBeenCalled();
  local.outcome = 'accepted';
  await user.click(expanded.getByRole('button', { name: 'world.emotes.title' }));
  await user.click(screen.getByRole('menuitem', { name: /world.emotes.thanks/ }));
  expect(local.gestures).toEqual(['wave', 'thanks']);
  expect(screen.getByRole('status')).toBeEmptyDOMElement();
  expect(expandedChange).toHaveBeenCalledExactlyOnceWith(false);
});
it('keeps the shared gesture controls open when the session refuses to send', async () => {
  const user = userEvent.setup();
  const expandedChange = vi.fn();
  const send = vi.fn(() => false);
  render(
    <WorldPrototype
      lng="fr"
      ownerId="owner"
      connected
      onEmote={send}
      hudExpanded
      onHudExpandedChange={expandedChange}
    />
  );
  const expanded = within(screen.getByTestId('expanded-controls'));
  await user.click(expanded.getByRole('button', { name: 'world.emotes.title' }));
  await user.click(screen.getByRole('menuitem', { name: /world.emotes.laugh/ }));
  expect(send).toHaveBeenCalledExactlyOnceWith('laugh');
  expect(local.gestures).toEqual([]);
  expect(expandedChange).not.toHaveBeenCalled();
});
