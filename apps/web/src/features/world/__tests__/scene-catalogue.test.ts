import { expect, it } from 'vitest';
import { WORLD } from '../definition';
import { sceneActivity } from '../scene-activities';
import { createSimulation, stepSimulation } from '../simulation';
import { SceneInteractions } from '../scene-interactions';
import { worldActions, functionPlace, functionSurface } from '../functions';
import { STATIC_SLASH_COMMAND_IDS } from '@/lib/slash-commands';
it('every authored activity has an accessible approach, a real native identity and a coherent place', () => {
  const keys = WORLD.props.flatMap(p => (p.key ? [p.key] : []));
  expect(new Set(keys).size).toBe(keys.length);
  for (const prop of WORLD.props) {
    const activity = sceneActivity(prop.id);
    if (!activity) continue;
    expect(prop.key, 'Activity identity survives rearranging its furniture').toBeTruthy();
    const sim = createSimulation(WORLD);
    let opened = false;
    const scene = new SceneInteractions(sim, {
      canOpen: () => true,
      open: () => {
        opened = true;
        return true;
      },
    });
    expect(scene.choose({ kind: 'object', id: prop.id }), prop.id).toBe(true);
    for (let n = 0; n < 3600 && !opened; n++) {
      stepSimulation(sim, 1 / 60, { x: 0, y: 0 });
      scene.update();
    }
    expect(opened, prop.id).toBe(true);
    const zone = WORLD.zones.find(
      z => prop.x >= z.x && prop.y >= z.y && prop.x < z.x + z.width && prop.y < z.y + z.height
    );
    if (activity.kind === 'native') {
      expect(functionSurface(activity.token)).toBe('activity');
      expect(functionPlace(activity.token), prop.id).toBe(zone?.id);
    } else if (activity.kind === 'command') {
      expect(STATIC_SLASH_COMMAND_IDS.has(activity.id)).toBe(true);
      expect(worldActions(k => k).find(a => a.id === activity.id)?.place, prop.id).toBe(zone?.id);
    }
  }
});
