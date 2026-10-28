import { WORLD } from './definition';
import { hasDecorScreen, type DecorPresentation, type ScreenVariant } from './decor-presentation';
export interface PhotoDecor {
  readonly id: string;
  readonly light?: boolean;
  readonly screen?: ScreenVariant;
}
const LAMPS = new Set(
  WORLD.props.filter(prop => prop.kind === 'lamp' || prop.kind === 'tablelamp').map(prop => prop.id)
);
const SCREENS = new Set(WORLD.props.filter(hasDecorScreen).map(prop => prop.id));
/** Reconstruct a finite public appearance, never serialise a runtime map or screen content. */
export function projectPhotoDecor(
  values: readonly (DecorPresentation & { id: string })[] = []
): readonly PhotoDecor[] {
  const result = new Map<string, PhotoDecor>();
  for (const value of values.slice(0, LAMPS.size + SCREENS.size)) {
    if (LAMPS.has(value.id) && typeof value.light === 'boolean')
      result.set(value.id, Object.freeze({ id: value.id, light: value.light }));
    if (SCREENS.has(value.id) && [0, 1, 2, 3, 4].includes(value.screen ?? -1))
      result.set(value.id, Object.freeze({ id: value.id, screen: value.screen }));
  }
  return Object.freeze([...result.values()]);
}
