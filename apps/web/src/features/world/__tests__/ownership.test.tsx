import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { StrictMode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WORLD } from '../definition';
import { useWorldRuntime } from '../useWorldRuntime';
import type { createRuntime, WorldRuntime } from '../runtime';
import type { WorldSnapshot } from '../types';

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
    setQuality: vi.fn(),
    setHome: vi.fn(),
    setAtmosphere: vi.fn(),
    setReducedMotion: vi.fn(),
    setPaused: vi.fn(),
    snapshot: () => INITIAL,
    destroy: vi.fn(),
  };
}
function Harness({ ownerId }: { ownerId: string }) {
  const { canvasRef, snapshot, failed, retry } = useWorldRuntime({
    ownerId,
    player: 'You',
    bip: 'BIP',
    quality: 'high',
    paused: false,
    reducedMotion: true,
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
