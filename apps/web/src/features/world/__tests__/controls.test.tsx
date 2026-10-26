import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { WorldMinimap } from '../WorldMinimap';
import { WorldJoystick } from '../WorldJoystick';
import { WORLD } from '../definition';
import type { WorldSnapshot } from '../types';

const snapshot: WorldSnapshot = {
  player: WORLD.spawn,
  bip: WORLD.bipSpawn,
  zone: 'arrival',
  zoom: 1,
  following: true,
  bipFollowing: false,
  metrics: { fps: 60, frameP95: 17, renderP95: 2, sprites: 20, textureBytes: 1000 },
};

describe('accessible world controls', () => {
  it('uses map clicks for the camera and keyboard activation for recentering', async () => {
    const explore = vi.fn(),
      recenter = vi.fn();
    render(
      <WorldMinimap
        snapshot={snapshot}
        label="Explore the map"
        onExplore={explore}
        onRecenter={recenter}
      />
    );
    const map = screen.getByRole('button', { name: 'Explore the map' });
    vi.spyOn(map, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, 148, 110));
    fireEvent.click(map, { detail: 1, clientX: 74, clientY: 55 });
    expect(explore).toHaveBeenCalledWith({ x: WORLD.width / 2, y: WORLD.height / 2 });
    map.focus();
    await userEvent.keyboard('{Enter}');
    expect(recenter).toHaveBeenCalledTimes(1);
    expect(explore).toHaveBeenCalledTimes(1);
  });

  it.each(['Move using the joystick or arrow keys', 'Déplacer avec le joystick ou les flèches'])(
    'names the joystick and releases a cancelled contact: %s',
    label => {
      const hold = vi.fn(),
        release = vi.fn();
      render(<WorldJoystick label={label} onHold={hold} onRelease={release} />);
      const right = screen.getByRole('button', { name: label });
      Object.defineProperties(right, {
        setPointerCapture: { value: vi.fn() },
        hasPointerCapture: { value: () => false },
      });
      fireEvent.pointerDown(right, { pointerId: 2, button: 0, clientX: 0, clientY: 0 });
      fireEvent.pointerMove(right, { pointerId: 2, clientX: 20, clientY: 0 });
      expect(hold).toHaveBeenCalledWith('joystick', { x: 1, y: 0 });
      fireEvent.pointerCancel(right, { pointerId: 2 });
      expect(release).toHaveBeenCalledWith('joystick');
      fireEvent.keyDown(right, { code: 'ArrowRight' });
      fireEvent.blur(right);
      expect(release).toHaveBeenCalledTimes(2);
    }
  );
});
