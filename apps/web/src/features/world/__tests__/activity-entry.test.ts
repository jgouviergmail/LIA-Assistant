import { expect, it } from 'vitest';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import de from '../../../../locales/de/translation.json';
import es from '../../../../locales/es/translation.json';
import itLocale from '../../../../locales/it/translation.json';
import zh from '../../../../locales/zh/translation.json';
import type { AppConfig } from '@/hooks/useAppConfig';
import {
  activityAvailable,
  activityEntry,
  workspaceAvailable,
  catalogueSelection,
  activityTitle,
} from '../activity-entry';
import { ACTIVITY_CATALOGUE } from '../activity-catalogue';

function config(features: Partial<AppConfig['features']> = {}): AppConfig {
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
      ...features,
    },
  };
}
it.each([
  ['en', en, 'Generate the image ', 'Call '],
  ['fr', fr, "Génère l'image ", 'Appelle '],
  ['de', de, 'Erzeuge das Bild ', 'Rufe '],
  ['es', es, 'Genera la imagen ', 'Llama a '],
  ['it', itLocale, "Genera l'immagine ", 'Chiama '],
  ['zh', zh, '生成图片 ', '拨打 '],
] as const)(
  'preserves explicit unsent prefixes, including the final space, in %s',
  (_, locale, image, call) => {
    const t = (key: string) => {
      if (key === 'world.activities.image_draft') return locale.world.activities.image_draft;
      if (key === 'world.activities.call_draft') return locale.world.activities.call_draft;
      return key;
    };
    expect(activityEntry({ kind: 'compose', id: 'image' }, t)).toEqual({
      selection: 'lia',
      draft: image,
    });
    expect(activityEntry({ kind: 'compose', id: 'call' }, t)).toEqual({
      selection: 'lia',
      draft: call,
    });
  }
);
it('keeps the requested gallery family as explicit host input and rejects unavailable bookmarks', () => {
  const policy = {
    native: new Set(['generated-assets'] as const),
    commands: new Set<string>(),
    radio: false,
    config: config(),
  };
  for (const tab of ['images', 'documents', 'screenshots', 'bookmarks'] as const)
    expect(activityEntry({ kind: 'gallery', tab }, key => key)).toEqual({
      selection: 'generated-assets',
      tab,
    });
  expect(activityAvailable({ kind: 'gallery', tab: 'bookmarks' }, policy)).toBe(false);
  expect(
    activityAvailable(
      { kind: 'gallery', tab: 'bookmarks' },
      { ...policy, config: config({ bookmarks_enabled: true }) }
    )
  ).toBe(true);
  expect(
    activityAvailable({ kind: 'gallery', tab: 'images' }, { ...policy, native: new Set() })
  ).toBe(false);
});
it('does not mount gated workspaces until the instance confirms the same native feature', () => {
  for (const id of ['meetings', 'workboard', 'sms'] as const) {
    expect(workspaceAvailable(id, null)).toBe(false);
    expect(workspaceAvailable(id, config())).toBe(false);
  }
  const enabled = config({ meetings_enabled: true, workboard_enabled: true, sms_enabled: true });
  for (const id of ['meetings', 'workboard', 'sms', 'relations', 'alerts', 'registers'] as const)
    expect(workspaceAvailable(id, enabled)).toBe(true);
});

it('opens full activity workspaces from discovery while preserving native configuration in settings', () => {
  for (const token of ['meetings', 'workboard', 'sms'] as const) {
    expect(catalogueSelection(token, false)).toBe('world-' + token);
    expect(catalogueSelection(token, true)).toBe(token);
  }
  expect(catalogueSelection('memories', false)).toBe('memories');
});
it('routes every authored activity family into its real host with a readable title and an unsent draft', () => {
  const t = (key: string) => key;
  const expected = {
    'arcade-tic-tac-toe': 'world-arcade',
    appearance: 'world-avatar',
    health: 'health-metrics',
    assets: 'generated-assets',
    sms: 'world-sms',
    radio: 'world-radio',
    'generate-image': 'lia',
    weather: 'lia',
  } as const;
  for (const key of Object.keys(expected) as (keyof typeof expected)[]) {
    const activity = ACTIVITY_CATALOGUE[key];
    expect(activityEntry(activity, t).selection).toBe(expected[key]);
    expect(activityTitle(activity, t).length).toBeGreaterThan(0);
  }
  expect(activityEntry('lia', t)).toEqual({ selection: 'lia-menu' });
  expect(activityEntry(ACTIVITY_CATALOGUE.weather, t).draft).toBe('chat.slash.weather_intent');
  expect(activityEntry({ kind: 'command', id: 'unknown' }, t).draft).toBeUndefined();
  expect(activityTitle({ kind: 'command', id: 'unknown' }, t)).toBe('');
  expect(activityTitle({ kind: 'workspace', id: 'registers' }, t)).toBe('registers.title');
});
it('applies current instance and native permissions to each activity family without hiding public composition', () => {
  const policy = {
    native: new Set(['health-metrics'] as const),
    commands: new Set(['weather']),
    radio: false,
    config: null,
  };
  for (const key of ['appearance', 'health', 'generate-image', 'weather'] as const)
    expect(activityAvailable(ACTIVITY_CATALOGUE[key], policy)).toBe(true);
  // An unconfirmed instance (no configuration yet) never offers the arcade.
  expect(activityAvailable(ACTIVITY_CATALOGUE['arcade-tic-tac-toe'], policy)).toBe(false);
  expect(
    activityAvailable(ACTIVITY_CATALOGUE['arcade-tic-tac-toe'], {
      ...policy,
      config: config({ world_arcade_enabled: true }),
    })
  ).toBe(true);
  expect(activityAvailable('lia', policy)).toBe(true);
  expect(activityAvailable(ACTIVITY_CATALOGUE.sms, policy)).toBe(false);
  expect(activityAvailable(ACTIVITY_CATALOGUE.memories, policy)).toBe(false);
  expect(activityAvailable(ACTIVITY_CATALOGUE.news, policy)).toBe(false);
  expect(activityAvailable(ACTIVITY_CATALOGUE.radio, policy)).toBe(false);
  expect(activityAvailable(ACTIVITY_CATALOGUE.radio, { ...policy, radio: true })).toBe(true);
  expect(
    activityAvailable(ACTIVITY_CATALOGUE['arcade-tic-tac-toe'], {
      ...policy,
      config: config({ world_arcade_enabled: false }),
    })
  ).toBe(false);
});
