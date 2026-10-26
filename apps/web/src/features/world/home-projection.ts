import type { Tone, WorldDefinition, WorldProp } from './types';

export interface HomeSkin {
  palette: Tone;
}

export function skinHomeProps(world: WorldDefinition, skin: HomeSkin | null): readonly WorldProp[] {
  const home = world.zones.find(zone => zone.id === 'home');
  if (!skin || !home) return world.props;
  return world.props.map(prop =>
    prop.x >= home.x &&
    prop.x < home.x + home.width &&
    prop.y >= home.y &&
    prop.y < home.y + home.height
      ? { ...prop, tone: skin.palette }
      : prop
  );
}
