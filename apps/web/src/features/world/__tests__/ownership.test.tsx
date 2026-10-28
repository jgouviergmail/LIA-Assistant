import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { StrictMode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WORLD } from '../definition';
import { useWorldRuntime } from '../useWorldRuntime';
import type { createRuntime, WorldRuntime } from '../runtime';
import type { WorldActingState, WorldSnapshot } from '../types';
import type { SceneHost } from '../scene-interactions';

const factory = vi.hoisted(() => vi.fn<typeof createRuntime>());
vi.mock('../runtime', () => ({ createRuntime: factory }));
const INITIAL: WorldSnapshot = {
  player: WORLD.spawn,
  bip: WORLD.bipSpawn,
  zone: 'arrival',
  zoom: 1,
  following: true,
  bipFollowing: false,
  metrics: { fps: 0, frameP95: 0, renderP95: 0, sprites: 0, textureBytes: 0 },
};
const options: Parameters<typeof createRuntime>[2][] = [];
const instances: WorldRuntime[] = [];
function instance(): WorldRuntime {
  return {
    photoScene: () => null,
    input: {
      direction: () => ({ x: 0, y: 0 }),
      hold: vi.fn(),
      release: vi.fn(),
      clear: vi.fn(),
      dispose: vi.fn(),
    },
    emote: vi.fn(() => 'accepted' as const),
    interact: vi.fn(),
    zoom: vi.fn(),
    recenter: vi.fn(),
    explore: vi.fn(),
    callBip: vi.fn(),
    setQuality: vi.fn(),
    setHome: vi.fn(),
    setAtmosphere: vi.fn(),
    setRouteVisible: vi.fn(),
    setPrivateSignals: vi.fn(),
    setActingSource: vi.fn(),
    setConversationOpen: vi.fn(),
    setSeason: vi.fn(),
    setReducedMotion: vi.fn(),
    setPaused: vi.fn(),
    snapshot: () => INITIAL,
    destroy: vi.fn(),
  };
}
function Harness({
  ownerId,
  scene,
  onActingState,
}: {
  ownerId: string;
  scene?: SceneHost;
  onActingState?: (state: WorldActingState) => void;
}) {
  const { canvasRef, snapshot, failed, retry } = useWorldRuntime({
    ownerId,
    player: 'You',
    bip: 'BIP',
    quality: 'high',
    paused: false,
    reducedMotion: true,
    conversationOpen: true,
    scene,
    onActingState,
  });
  return (
    <>
      <canvas ref={canvasRef} aria-label="Owned world surface" />
      <output aria-label="FPS">{snapshot.metrics.fps}</output>
      {failed && <p role="alert">Unavailable</p>}
      <button onClick={retry}>Retry</button>
    </>
  );
}
beforeEach(() => {
  options.length = 0;
  instances.length = 0;
  factory.mockReset();
  factory.mockImplementation((_canvas, _world, value) => {
    options.push(value);
    const current = instance();
    instances.push(current);
    return current;
  });
});
describe('world owner lifetime', () => {
  it('publishes only current acting evidence to the latest observer without replacing its clock', () => {
    const first = vi.fn();
    const latest = vi.fn();
    const { rerender } = render(<Harness ownerId="first" onActingState={first} />);
    rerender(<Harness ownerId="first" onActingState={latest} />);
    expect(instances).toHaveLength(1);
    act(() => options[0].onSnapshot({ ...INITIAL, acting: 'waiting' }));
    expect(first).not.toHaveBeenCalled();
    expect(latest).toHaveBeenLastCalledWith('waiting');
    rerender(<Harness ownerId="second" onActingState={latest} />);
    latest.mockClear();
    act(() => options[0].onSnapshot({ ...INITIAL, acting: 'success' }));
    expect(latest).not.toHaveBeenCalled();
    act(() => options[1].onSnapshot({ ...INITIAL, acting: 'idle' }));
    expect(latest).toHaveBeenLastCalledWith('idle');
  });
  it('reapplies current visual preferences and framing when scene ports replace the runtime', () => {
    const first: SceneHost = { canOpen: () => true, open: () => true };
    const second: SceneHost = { canOpen: () => true, open: () => true };
    const { rerender } = render(<Harness ownerId="owner" scene={first} />);
    expect(instances[0].setConversationOpen).toHaveBeenLastCalledWith(true);
    rerender(<Harness ownerId="owner" scene={second} />);
    expect(instances).toHaveLength(2);
    expect(instances[0].destroy).toHaveBeenCalledOnce();
    expect(instances[1].setConversationOpen).toHaveBeenLastCalledWith(true);
    expect(instances[1].setReducedMotion).toHaveBeenLastCalledWith(true);
    expect(instances[1].setQuality).toHaveBeenLastCalledWith('high');
  });
  it('releases an old owner, reapplies preferences and refuses its late snapshots', () => {
    const { rerender, unmount } = render(<Harness ownerId="first" />);
    expect(instances[0].setQuality).toHaveBeenLastCalledWith('high');
    rerender(<Harness ownerId="second" />);
    expect(instances[0].destroy).toHaveBeenCalledTimes(1);
    expect(instances[1].setQuality).toHaveBeenLastCalledWith('high');
    expect(instances[1].setReducedMotion).toHaveBeenLastCalledWith(true);
    act(() => options[0].onSnapshot({ ...INITIAL, metrics: { ...INITIAL.metrics, fps: 999 } }));
    expect(screen.getByLabelText('FPS')).toHaveTextContent('0');
    act(() => options[1].onSnapshot({ ...INITIAL, metrics: { ...INITIAL.metrics, fps: 37 } }));
    expect(screen.getByLabelText('FPS')).toHaveTextContent('37');
    unmount();
    expect(instances[1].destroy).toHaveBeenCalledTimes(1);
  });

  it('tears down every Strict Mode runtime exactly once', () => {
    const { unmount } = render(
      <StrictMode>
        <Harness ownerId="owner" />
      </StrictMode>
    );
    expect(instances.length).toBeGreaterThan(1);
    for (const old of instances.slice(0, -1)) expect(old.destroy).toHaveBeenCalledTimes(1);
    unmount();
    for (const current of instances) expect(current.destroy).toHaveBeenCalledTimes(1);
  });

  it('offers recovery after a failed graphics initialization', async () => {
    factory.mockImplementationOnce(() => {
      throw new Error('Graphics unavailable');
    });
    render(<Harness ownerId="owner" />);
    await expect(screen.findByRole('alert')).resolves.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(instances).toHaveLength(1);
  });
});
