import { canvasContext } from '@/__tests__/fixtures/canvas-context';
import { afterEach, expect, it, vi } from 'vitest';
import { paintEmote } from '../art/emotes';
import { WorldRenderer } from '../renderer';
import { createSimulation } from '../simulation';
import { createCamera, project } from '../geometry';
import { WORLD } from '../definition';
import { EMOTE_SECONDS } from '../emote-catalogue';
import { avatarLabelOffset } from '../art/person-accessories';
import { DEFAULT_AVATAR } from '../avatar-catalogue';

// The lower edge of every name plate the renderer draws (standing, tall headwear, lying).
const PLATES = [
  { name: 'default', bottom: -avatarLabelOffset() + 11 },
  { name: 'hat', bottom: -avatarLabelOffset({ ...DEFAULT_AVATAR, headwear: 'hat' }) + 11 },
  { name: 'mohawk', bottom: -avatarLabelOffset({ ...DEFAULT_AVATAR, hair: 'mohawk' }) + 11 },
  { name: 'lying', bottom: -104 + 8 },
];
it('keeps the entire gesture inside the actor layer and strictly below the name plate at every phase', () => {
  const c = canvasContext({});
  const boxes = vi.spyOn(c, 'roundRect');
  const event = { kind: 'wave' as const, serial: 1, started: 0, until: EMOTE_SECONDS };
  for (const plate of PLATES)
    for (const reduced of [true, false])
      for (let step = 0; step < 20; step++) {
        boxes.mockClear();
        paintEmote(c, { x: 0, y: 0 }, event, (step / 20) * EMOTE_SECONDS, reduced, plate.bottom);
        const [x, y, width, height] = boxes.mock.calls[0];
        expect(x).toBeGreaterThanOrEqual(-79);
        expect(x + width).toBeLessThanOrEqual(79);
        expect(y, plate.name).toBeGreaterThan(plate.bottom);
        expect(y).toBeGreaterThanOrEqual(-112);
        expect(y + height).toBeLessThanOrEqual(47);
      }
  boxes.mockClear();
  paintEmote(c, { x: 0, y: 0 }, event, EMOTE_SECONDS, false, PLATES[0].bottom);
  expect(boxes).not.toHaveBeenCalled();
  boxes.mockRestore();
});
afterEach(() => vi.restoreAllMocks());
it('draws a live gesture below the name plate the renderer actually painted for that actor', () => {
  const roundRect = vi.fn();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
    canvasContext({ roundRect, measureText: () => ({ width: 40 }) as TextMetrics })
  );
  const sim = createSimulation(WORLD);
  sim.bip.position = { x: -1000, y: -1000 };
  const now = performance.now() / 1000;
  sim.player.emote = { kind: 'wave', serial: 1, started: now - 0.5, until: now + 1.5 };
  const renderer = new WorldRenderer(document.createElement('canvas'), WORLD, 'low', {
    player: 'Léa',
    bip: 'LIA',
  });
  renderer.resize(800, 600);
  renderer.render(createCamera({ width: 800, height: 600 }, sim.player.position), sim);
  const at = project(sim.player.position);
  const plate = roundRect.mock.calls.find(([x, , w]) => x === at.x - w / 2 && w === 58);
  const bubble = roundRect.mock.calls.find(
    ([x, , w, h]) => x === at.x + 23 && w === 34 && h === 30
  );
  if (!plate || !bubble) throw new Error('Missing plate or gesture');
  expect(bubble[1]).toBeGreaterThan(plate[1] + plate[3]);
  renderer.destroy();
});
