import { expect, it } from 'vitest';
import type { AppConfig } from '@/hooks/useAppConfig';
import { WORLD } from '../definition';
import { compileGameCabinets, CABINET_GAMES } from '../game-catalogue';
import { objectApproaches } from '../scene-interactions';
import { sceneActivity } from '../scene-activities';
import { activityEntry, activityTitle, activityAvailable } from '../activity-entry';

function config(world_arcade_enabled?: boolean): AppConfig {
  return {
    api_version: 'test',
    sse: { heartbeat_interval_seconds: 30 },
    rate_limits: { enabled: true, per_minute: 60, burst: 5 },
    i18n: { supported_languages: ['en'], default_language: 'en' },
    features: {
      tool_approval_enabled: true,
      attachments_enabled: false,
      rag_spaces_enabled: false,
      rag_spaces_embedding_model: 'test',
      journals_enabled: false,
      world_arcade_enabled,
    },
  };
}
it('uses the same authored playable approach from every direction and resolves each actual cabinet', () => {
  for (const cabinet of compileGameCabinets(WORLD)) {
    const prop = WORLD.props.find(item => item.id === cabinet.prop);
    if (!prop) throw new Error('fixture');
    for (const from of [
      { x: 1, y: 1 },
      { x: 70, y: 80 },
      { x: 70, y: 1 },
      { x: 1, y: 80 },
    ])
      expect(objectApproaches(prop, from)).toEqual([cabinet.approach]);
    const activity = { kind: 'arcade' as const, id: cabinet.id };
    expect(sceneActivity(cabinet.prop)).toEqual(activity);
    expect(activityEntry(activity, key => key)).toEqual({
      selection: 'world-arcade',
      cabinet: cabinet.id,
    });
    expect(activityTitle(activity, key => key)).toBe(
      `world.arcade.games.${CABINET_GAMES[cabinet.id]}.title`
    );
    const policy = { native: new Set<never>(), commands: new Set<string>(), radio: false };
    // An arcade is offered only once the instance has confirmed the feature.
    expect(activityAvailable(activity, { ...policy, config: null })).toBe(false);
    expect(activityAvailable(activity, { ...policy, config: config() })).toBe(false);
    expect(activityAvailable(activity, { ...policy, config: config(false) })).toBe(false);
    expect(activityAvailable(activity, { ...policy, config: config(true) })).toBe(true);
  }
});
