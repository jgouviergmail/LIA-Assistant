/** Voice choices play one native, local WAV; every API/provider boundary stays mocked. */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import type { Locator, Page } from '@playwright/test';

import {
  test,
  expect,
  idleNotificationStream,
  waitForHydration,
  waitForMockGate,
  type MockRoute,
} from '../fixtures';
import { surfaceRoutes } from '../fixtures/settings-surfaces';
import {
  MATERIAL_SYMBOLS_STYLESHEET_URL,
  MATERIAL_SYMBOLS_FONT_URL,
} from '../fixtures/offline-fonts';
import {
  radioOptions,
  radioPreferences,
  radioSources,
} from '../../src/lib/radio/__tests__/fixtures';
import type { RadioPreferences, RadioSpeakingRole } from '../../src/lib/radio/types';
import type { LiaVoiceChoice, LiaVoices } from '../../src/types/lia-voices';
import { expectNoOverflow, prepareTheme } from './overflow-report';

declare global {
  interface Window {
    settingsVoiceSampleProbe: {
      audio: HTMLAudioElement[];
      events: Array<{ audio: number; type: string }>;
    };
  }
}

const SAMPLE = 'settings.voice_sample';
const LIA = 'settings.voice_mode.lia_voices';
// These are DENIED native browser transports, as in meeting-timeline.spec.ts.
// All external page/worker requests are checked independently below, against
// only the two exact font URLs fulfilled by the offline font fixture.
const EXPECTED_BLOCKED_BROWSER_TRANSPORTS = new Set([
  'CONNECT www.google.com:443',
  'CONNECT content-autofill.googleapis.com:443',
  'CONNECT fonts.googleapis.com:443',
  'CONNECT fonts.gstatic.com:443',
]);
const RADIO_ROLES: RadioSpeakingRole[] = [
  'host',
  'anchor',
  'expert',
  'columnist',
  'speaker_a',
  'speaker_b',
  'speaker_c',
];
const radioVoices = RADIO_ROLES.map(role => ({
  voice_id: `fr-${role}`,
  label: `Voix ${role}`,
  gender: null,
  language: 'fr',
}));
const maleDefault = { voice_id: 'fr-default-male', label: 'Paul', gender: 'male', language: 'fr' };
const femaleDefault = {
  voice_id: 'fr-default-female',
  label: 'Léa',
  gender: 'female',
  language: 'fr',
};
const liaVoices: LiaVoices = {
  available: true,
  engine: 'edge/edge-tts',
  provider: 'edge',
  male: null,
  female: null,
  default_male: maleDefault,
  default_female: femaleDefault,
  voices: [
    maleDefault,
    femaleDefault,
    { voice_id: 'fr-male-one', label: 'Bruno', gender: 'male', language: 'fr' },
    { voice_id: 'fr-male-two', label: 'Antoine', gender: 'male', language: 'fr' },
    { voice_id: 'fr-female-one', label: 'Claire', gender: 'female', language: 'fr' },
    { voice_id: 'en-male', label: 'John', gender: 'male', language: 'en' },
  ],
};

function copy(key: string, values: Record<string, string> = {}): string {
  let value: unknown = JSON.parse(
    readFileSync(path.join(__dirname, '../../locales/fr/translation.json'), 'utf8')
  );
  for (const part of key.split('.')) {
    if (typeof value !== 'object' || value === null) throw new Error(`Missing French copy ${key}`);
    value = (value as Record<string, unknown>)[part];
  }
  if (typeof value !== 'string') throw new Error(`Missing French copy ${key}`);
  return value.replace(/{{(\w+)}}/g, (_, name: string) => values[name] ?? `{{${name}}}`);
}

/** A non-silent PCM16 WAV, decoded and clocked by the browser's actual media pipeline. */
function wave(seconds = 8): string {
  const rate = 16_000;
  const frames = seconds * rate;
  const wav = Buffer.alloc(44 + frames * 2);
  wav.write('RIFF');
  wav.writeUInt32LE(wav.length - 8, 4);
  wav.write('WAVEfmt ', 8);
  wav.writeUInt32LE(16, 16);
  wav.writeUInt16LE(1, 20);
  wav.writeUInt16LE(1, 22);
  wav.writeUInt32LE(rate, 24);
  wav.writeUInt32LE(rate * 2, 28);
  wav.writeUInt16LE(2, 32);
  wav.writeUInt16LE(16, 34);
  wav.write('data', 36);
  wav.writeUInt32LE(frames * 2, 40);
  for (let index = 0; index < frames; index++)
    wav.writeInt16LE(
      Math.round(1000 * Math.sin((2 * Math.PI * 440 * index) / rate)),
      44 + index * 2
    );
  return wav.toString('base64');
}

const WAV = wave();
function sample(voice: string, audio = WAV) {
  return { audio_base64: audio, mime_type: 'audio/wav', voice_id: voice };
}

async function ready(page: Page, panel: 'voice-mode' | 'radio'): Promise<Locator> {
  const response = await page.goto(`/fr/dashboard/settings?section=${panel}`);
  expect(response?.status(), 'the settings document loads').toBe(200);
  await waitForHydration(page, `#settings-section-${panel}`);
  const section = page.locator(`#settings-section-${panel}`);
  await expect(section).toBeVisible();
  await page.waitForFunction(
    () =>
      getComputedStyle(document.documentElement).getPropertyValue('--color-background').trim() !==
      ''
  );
  if (panel === 'radio')
    await section
      .locator('summary')
      .filter({ hasText: copy('radio.settings.voices.title') })
      .click();
  await expect(section.getByRole('combobox').first()).toBeVisible();
  return section;
}

async function choose(page: Page, control: Locator, label: string): Promise<void> {
  await control.click();
  await page.getByRole('option', { name: label, exact: true }).click();
  await expect(control).toBeFocused();
}

async function nativePlaying(page: Page, count: number): Promise<void> {
  await expect
    .poll(() => page.evaluate(() => window.settingsVoiceSampleProbe.audio.length))
    .toBe(count);
  await expect
    .poll(() =>
      page.evaluate(() => {
        const audio = window.settingsVoiceSampleProbe.audio.at(-1);
        return (
          audio !== undefined &&
          !audio.paused &&
          audio.currentTime > 0.1 &&
          audio.duration > 1 &&
          audio.readyState >= 2 &&
          window.settingsVoiceSampleProbe.audio.every(held => held === audio || held.paused)
        );
      })
    )
    .toBe(true);
}

async function allPaused(page: Page): Promise<void> {
  await expect
    .poll(() =>
      page.evaluate(() => window.settingsVoiceSampleProbe.audio.every(audio => audio.paused))
    )
    .toBe(true);
}

async function leaveVoicePanel(page: Page): Promise<void> {
  await page.getByRole('button', { name: copy('settings.theme.title'), exact: true }).click();
  await expect(page.locator('#settings-section-theme')).toBeVisible();
  await allPaused(page);
}

function saveMocks(): MockRoute[] {
  let lia = { ...liaVoices };
  return [
    {
      url: '**/api/v1/voice/lia-voices',
      method: 'GET',
      handler: route => route.fulfill({ json: lia }),
    },
    {
      url: '**/api/v1/voice/lia-voices',
      method: 'PUT',
      handler: async route => {
        const choice: LiaVoiceChoice = route.request().postDataJSON();
        lia = { ...lia, ...choice };
        await route.fulfill({ json: lia });
      },
    },
    { url: '**/api/v1/radio/options', json: radioOptions({ voices: radioVoices }) },
    { url: '**/api/v1/radio/preferences', method: 'GET', json: radioPreferences() },
    {
      url: '**/api/v1/radio/preferences',
      method: 'PUT',
      handler: route => route.fulfill({ json: route.request().postDataJSON() }),
    },
    { url: '**/api/v1/radio/sources', json: radioSources({ base: [], own: [] }) },
  ];
}

const observations = new WeakMap<
  Page,
  { unexpectedApi: string[]; errors: string[]; external: string[] }
>();

test.beforeEach(async ({ page, context, authenticate, mockApi }) => {
  await page.addInitScript(() => {
    localStorage.setItem(
      'lia_eyes_widget_prefs',
      JSON.stringify({ state: { visible: false }, version: 0 })
    );
    const probe = {
      audio: [] as HTMLAudioElement[],
      events: [] as Array<{ audio: number; type: string }>,
    };
    window.settingsVoiceSampleProbe = probe;
    const NativeAudio = window.Audio;
    window.Audio = class extends NativeAudio {
      constructor(src?: string) {
        super(src);
        const index = probe.audio.push(this) - 1;
        for (const type of ['playing', 'pause', 'ended', 'error'])
          this.addEventListener(type, () => probe.events.push({ audio: index, type }));
      }
    };
  });
  const observed = {
    unexpectedApi: [] as string[],
    errors: [] as string[],
    external: [] as string[],
  };
  observations.set(page, observed);
  context.on('request', request => {
    const url = new URL(request.url());
    if (
      (url.protocol === 'http:' || url.protocol === 'https:') &&
      url.hostname !== 'localhost' &&
      url.hostname !== '127.0.0.1'
    )
      observed.external.push(request.url());
  });
  page.on('response', response => {
    if (response.status() === 501 && new URL(response.url()).pathname.startsWith('/api/'))
      observed.unexpectedApi.push(response.url());
  });
  page.on('pageerror', error => observed.errors.push(error.message));
  await authenticate({ language: 'fr', voice_enabled: false, theme: 'light' });
  await mockApi([...surfaceRoutes, ...saveMocks(), idleNotificationStream]);
});

test.afterEach(async ({ page, apiNetworkGuard }, info) => {
  const observed = observations.get(page)!;
  const media = await page.evaluate(() => ({
    events: window.settingsVoiceSampleProbe?.events ?? [],
    audio: (window.settingsVoiceSampleProbe?.audio ?? []).map(audio => ({
      paused: audio.paused,
      ended: audio.ended,
      time: audio.currentTime,
      duration: Number.isFinite(audio.duration) ? audio.duration : null,
      readyState: audio.readyState,
      error: audio.error?.code ?? null,
    })),
  }));
  await info.attach('voice-sample-isolation.json', {
    body: JSON.stringify({ ...observed, media, blockedTransport: apiNetworkGuard.blockedRequests }),
    contentType: 'application/json',
  });
  expect(observed.unexpectedApi, 'every backend operation is mocked').toEqual([]);
  expect(observed.errors, 'no uncaught application error').toEqual([]);
  expect(
    observed.external.filter(
      url => url !== MATERIAL_SYMBOLS_STYLESHEET_URL && url !== MATERIAL_SYMBOLS_FONT_URL
    ),
    'the app may request only the two exact externally named, locally mocked font URLs'
  ).toEqual([]);
  expect(
    apiNetworkGuard.blockedRequests.filter(
      request => !EXPECTED_BLOCKED_BROWSER_TRANSPORTS.has(request)
    ),
    'no API or provider transport may escape page interception'
  ).toEqual([]);
});

test('chat voices: only a choice starts playback, both genders and the administrator default can be heard', async ({
  page,
  mockApi,
}, info) => {
  const requests: unknown[] = [];
  await mockApi([
    {
      url: '**/api/v1/voice/lia-voices/sample',
      method: 'POST',
      handler: async route => {
        const body: { gender: string; voice_id: string | null } = route.request().postDataJSON();
        requests.push(body);
        await route.fulfill({ json: sample(body.voice_id ?? maleDefault.voice_id) });
      },
    },
  ]);
  const section = await ready(page, 'voice-mode');
  await expect(section.getByText(copy(`${SAMPLE}.hint`))).toBeVisible();
  expect(requests).toEqual([]);
  expect(await page.evaluate(() => window.settingsVoiceSampleProbe.audio.length)).toBe(0);
  const filter = section.getByRole('switch', {
    name: copy('settings.voice_language_filter.only_language', { language: 'français' }),
  });
  await filter.click();
  expect(requests).toEqual([]);
  expect(await page.evaluate(() => window.settingsVoiceSampleProbe.audio.length)).toBe(0);
  const male = section.getByRole('combobox', { name: copy(`${LIA}.male`) });
  await male.focus();
  await male.press('Enter');
  await expect(
    page.getByRole('option', {
      name: copy(`${LIA}.default`, { name: maleDefault.label }),
      exact: true,
    })
  ).toBeFocused();
  await page.keyboard.press('ArrowDown');
  await expect(page.getByRole('option', { name: 'Paul', exact: true })).toBeFocused();
  await page.keyboard.press('ArrowDown');
  await expect(page.getByRole('option', { name: 'Bruno', exact: true })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(male).toBeFocused();
  await expect(male).toHaveText('Bruno');
  await nativePlaying(page, 1);
  expect(requests).toEqual([{ gender: 'male', voice_id: 'fr-male-one' }]);
  await section.getByRole('button', { name: copy(`${SAMPLE}.stop`), exact: true }).click();
  await allPaused(page);
  await choose(page, male, copy(`${LIA}.default`, { name: maleDefault.label }));
  await nativePlaying(page, 2);
  expect(requests.at(-1)).toEqual({ gender: 'male', voice_id: null });
  const female = section.getByRole('combobox', { name: copy(`${LIA}.female`) });
  await choose(page, female, 'Claire');
  await nativePlaying(page, 3);
  expect(requests.at(-1)).toEqual({ gender: 'female', voice_id: 'fr-female-one' });
  await section.screenshot({ path: info.outputPath('chat-voice-sample-desktop.png') });
  await leaveVoicePanel(page);
  expect(requests).toHaveLength(3);
});

test('radio at 390px: all seven roles and automatic selection play the full current voice mapping', async ({
  page,
  mockApi,
}, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await prepareTheme(page, 'light');
  const requests: Array<{ role: RadioSpeakingRole; voices: RadioPreferences['voices'] }> = [];
  await mockApi([
    {
      url: '**/api/v1/radio/voices/sample',
      method: 'POST',
      handler: async route => {
        const body: { role: RadioSpeakingRole; voices: RadioPreferences['voices'] } = route
          .request()
          .postDataJSON();
        requests.push(body);
        await route.fulfill({ json: sample(body.voices[body.role] ?? 'fr-automatic') });
      },
    },
  ]);
  const section = await ready(page, 'radio');
  expect(requests).toEqual([]);
  const expected: RadioPreferences['voices'] = {};
  const currentPlayback = async (role: RadioSpeakingRole) => {
    const group = section.getByRole('group', { name: copy(`radio.roles.${role}`), exact: true });
    const control = group.getByRole('combobox', { name: copy(`radio.roles.${role}`), exact: true });
    const stop = group.getByRole('button', { name: copy(`${SAMPLE}.stop`), exact: true });
    await expect(
      section.getByRole('button', { name: copy(`${SAMPLE}.stop`), exact: true })
    ).toHaveCount(1);
    await expect(stop).toBeVisible();
    const selectBox = await control.boundingBox();
    const stopBox = await stop.boundingBox();
    expect(selectBox).not.toBeNull();
    expect(stopBox).not.toBeNull();
    expect(stopBox!.y).toBeGreaterThanOrEqual(selectBox!.y + selectBox!.height);
    expect(
      stopBox!.y - selectBox!.y - selectBox!.height,
      'Stop follows the chosen voice inside its own card, within a normal spacing gap'
    ).toBeLessThanOrEqual(16);
    return group;
  };
  for (const [index, role] of RADIO_ROLES.entries()) {
    const control = section.getByRole('combobox', {
      name: copy(`radio.roles.${role}`),
      exact: true,
    });
    await choose(page, control, `Voix ${role}`);
    expected[role] = `fr-${role}`;
    await nativePlaying(page, index + 1);
    expect(requests.at(-1)).toEqual({ role, voices: expected });
    const group = await currentPlayback(role);
    if (role === 'host' || role === 'speaker_c') {
      await group.scrollIntoViewIfNeeded();
      await expect(
        group.getByRole('button', { name: copy(`${SAMPLE}.stop`), exact: true })
      ).toBeInViewport();
      await page.screenshot({ path: info.outputPath(`radio-sample-${role}-mobile.png`) });
    }
  }
  await choose(
    page,
    section.getByRole('combobox', { name: copy('radio.roles.host'), exact: true }),
    copy('radio.settings.voices.automatic')
  );
  delete expected.host;
  await nativePlaying(page, 8);
  expect(requests.at(-1)).toEqual({ role: 'host', voices: expected });
  await currentPlayback('host');
  await expectNoOverflow(page, 'radio voice choices at 390px');
  await section.screenshot({ path: info.outputPath('radio-voice-sample-mobile.png') });
  await section.getByRole('button', { name: copy(`${SAMPLE}.stop`), exact: true }).click();
  await allPaused(page);
});

test('chat rapid choices: the latest alone plays, and leaving cancels an unfinished sample', async ({
  page,
  mockApi,
}) => {
  let firstRelease: () => void = () => undefined;
  const first = new Promise<void>(resolve => {
    firstRelease = resolve;
  });
  let leavingRelease: () => void = () => undefined;
  const leaving = new Promise<void>(resolve => {
    leavingRelease = resolve;
  });
  const requests: string[] = [];
  const cancellations: Array<string | null> = [];
  page.on('requestfailed', request => {
    if (new URL(request.url()).pathname !== '/api/v1/voice/lia-voices/sample') return;
    const body: { gender: string; voice_id: string | null } = request.postDataJSON();
    cancellations.push(body.voice_id);
  });
  await mockApi([
    {
      url: '**/api/v1/voice/lia-voices/sample',
      method: 'POST',
      handler: async (route, signal) => {
        const body: { gender: string; voice_id: string | null } = route.request().postDataJSON();
        const voice = body.voice_id ?? maleDefault.voice_id;
        requests.push(voice);
        if (voice === 'fr-male-one' && !(await waitForMockGate(first, signal))) return;
        if (voice === 'fr-female-one' && !(await waitForMockGate(leaving, signal))) return;
        await route.fulfill({ json: sample(voice) });
      },
    },
  ]);
  const section = await ready(page, 'voice-mode');
  const male = section.getByRole('combobox', { name: copy(`${LIA}.male`) });
  await choose(page, male, 'Bruno');
  await expect.poll(() => requests.length).toBe(1);
  await choose(page, male, 'Antoine');
  await nativePlaying(page, 2);
  await expect.poll(() => cancellations).toContain('fr-male-one');
  firstRelease();
  await expect(male).toHaveText('Antoine');
  await expect
    .poll(() => page.evaluate(() => window.settingsVoiceSampleProbe.audio.length))
    .toBe(2);
  await choose(page, section.getByRole('combobox', { name: copy(`${LIA}.female`) }), 'Claire');
  await expect.poll(() => requests.length).toBe(3);
  await leaveVoicePanel(page);
  await expect.poll(() => cancellations).toContain('fr-female-one');
  leavingRelease();
  await expect
    .poll(() => page.evaluate(() => window.settingsVoiceSampleProbe.audio.length))
    .toBe(3);
  expect(requests).toEqual(['fr-male-one', 'fr-male-two', 'fr-female-one']);
});

test('radio failures stay beside the player; retry preserves the saved choice and closing Voix stops sound', async ({
  page,
  mockApi,
}) => {
  const requests: unknown[] = [];
  const saves: RadioPreferences[] = [];
  await mockApi([
    {
      url: '**/api/v1/radio/preferences',
      method: 'PUT',
      handler: async route => {
        const preferences: RadioPreferences = route.request().postDataJSON();
        saves.push(preferences);
        await route.fulfill({ json: preferences });
      },
    },
    {
      url: '**/api/v1/radio/voices/sample',
      method: 'POST',
      handler: async route => {
        requests.push(route.request().postDataJSON());
        if (requests.length === 1) {
          await route.fulfill({
            status: 503,
            json: { detail: { code: 'voice_sample_unavailable' } },
          });
          return;
        }
        await route.fulfill({
          json: sample(
            'fr-host',
            requests.length === 3 ? Buffer.from('not a WAV').toString('base64') : WAV
          ),
        });
      },
    },
  ]);
  const section = await ready(page, 'radio');
  const host = section.getByRole('combobox', { name: copy('radio.roles.host'), exact: true });
  await choose(page, host, 'Voix host');
  const failure = section.getByRole('alert').filter({ hasText: copy(`${SAMPLE}.failed`) });
  await expect(failure).toBeVisible();
  await expect(host).toHaveText('Voix host');
  await expect(host).toBeFocused();
  await expect.poll(() => saves.length).toBe(1);
  const listen = section.getByRole('button', { name: copy(`${SAMPLE}.listen`), exact: true });
  await listen.click();
  await nativePlaying(page, 2);
  expect(requests[1]).toEqual(requests[0]);
  expect(saves).toHaveLength(1);
  await section.getByRole('button', { name: copy(`${SAMPLE}.stop`), exact: true }).click();
  await allPaused(page);
  await listen.click();
  await expect(failure).toBeVisible();
  await expect(host).toHaveText('Voix host');
  await listen.click();
  await nativePlaying(page, 4);
  await section
    .locator('summary')
    .filter({ hasText: copy('radio.settings.voices.title') })
    .click();
  await allPaused(page);
  expect(saves).toHaveLength(1);
});
