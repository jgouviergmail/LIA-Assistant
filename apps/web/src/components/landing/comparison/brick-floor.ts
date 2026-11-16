/**
 * The living map's brick count, as the thesis states it.
 *
 * The positioning reads « {{count}}+ »: the count is floored to ten, so 60 to
 * 69 bricks all say « 60+ » and the copy stays true as bricks are added,
 * without anyone editing it (owner, 2026-11-15). Only the language-neutral
 * structure of the map is read here, never its texts.
 */

import functional from '@/data/maps/functional.json';

export function brickCountFloor(): number {
  return Math.floor(functional.bricks.length / 10) * 10;
}
