import { test, expect } from '../fixtures';
import { installSoundOracle, installAudioProbe } from '../fixtures/world-sound';
import { SOUND_FILES } from '../../src/features/world/audio/catalogue';
import { cosmeticCue } from '../../src/features/world/audio/cosmetic-cues';
import { COSMETIC_ACTIONS } from '../../src/features/world/cosmetic-interactions';
import { WORLD } from '../../src/features/world/definition';

/** The short cues are exactly what a cosmetic interaction can play, read from its own table. */
const EFFECTS: ReadonlySet<string> = new Set(
  [...COSMETIC_ACTIONS, 'bird' as const]
    .flatMap(action =>
      action === 'machine'
        ? WORLD.props
            .filter(prop => prop.kind === 'machine')
            .map(prop => cosmeticCue(action, prop.id))
        : [cosmeticCue(action)]
    )
    .filter(id => id !== null)
);

test('qualify actual sound decoding or explicit unsupported browser audio', async ({
  page,
}, info) => {
  await installAudioProbe(page);
  await installSoundOracle(page);
  const supported = await page.evaluate(() => typeof AudioContext === 'function');
  if (!supported) {
    expect(
      await page.evaluate(() => new window.worldSoundOracle.BrowserWorldAudio().activate())
    ).toBe(false);
    await info.attach('audio-capability', {
      body: 'This browser engine does not expose Web Audio. The application must stay silent and report unavailability.',
      contentType: 'text/plain',
    });
    return;
  }
  await page.evaluate(() => {
    const button = document.querySelector('button');
    if (button)
      button.onclick = () => {
        const c = new AudioContext();
        void c.resume();
      };
  });
  await page.getByRole('button', { name: 'Enable original ambience' }).click();
  const result = await page.evaluate(async () => {
    const a = window.worldSoundOracle,
      context = window.worldSoundProbe.context,
      clips = [];
    if (!context) throw new Error('Audio context unavailable after gesture');
    for (const id of Object.keys(a.SOUND_FILES) as (keyof typeof a.SOUND_FILES)[]) {
      const response = await fetch(a.soundUrl(id));
      if (!response.ok) throw new Error(id + ' unavailable');
      const bytes = await response.arrayBuffer();
      const buffer = await context.decodeAudioData(bytes);
      const values = buffer.getChannelData(0);
      let energy = 0,
        peak = 0;
      for (const v of values) {
        energy += v * v;
        peak = Math.max(peak, Math.abs(v));
      }
      clips.push({
        id,
        encoded: bytes.byteLength,
        duration: buffer.duration,
        channels: buffer.numberOfChannels,
        decoded: buffer.length * buffer.numberOfChannels * 4,
        rms: Math.sqrt(energy / values.length),
        peak,
        seamJump: Math.abs(values[0] - values[values.length - 1]),
      });
    }
    await context.close();
    return clips;
  });
  // Every catalogued clip decoded, and every cue a scene can play is one of them.
  expect(result.map(clip => clip.id).sort()).toEqual(Object.keys(SOUND_FILES).sort());
  expect(EFFECTS.size).toBeGreaterThan(0);
  expect([...EFFECTS].filter(id => !Object.hasOwn(SOUND_FILES, id))).toEqual([]);
  for (const clip of result) {
    expect(clip.channels, clip.id).toBe(1);
    expect(clip.encoded, clip.id).toBeLessThan(512 * 1024);
    expect(clip.decoded, clip.id).toBeLessThan(8 * 1024 * 1024);
    const effect = EFFECTS.has(clip.id);
    expect(clip.duration, clip.id).toBeGreaterThan(
      effect ? 0.45 : clip.id === 'message' ? 0.8 : clip.id === 'phone' ? 4.8 : 29.8
    );
    expect(clip.duration, clip.id).toBeLessThan(
      effect ? 2.6 : clip.id === 'message' ? 1.3 : clip.id === 'phone' ? 5.3 : 30.3
    );
    expect(clip.rms, clip.id).toBeGreaterThan(0.0001);
    expect(clip.peak, clip.id).toBeLessThan(0.9);
    if (clip.id === 'arcade') expect(clip.seamJump).toBeLessThan(0.03);
  }
  await info.attach('decoded-sound-levels', {
    body: JSON.stringify(result, null, 2),
    contentType: 'application/json',
  });
});

test('real audio lifecycle or a clean unavailable result without audio support', async ({
  page,
}, info) => {
  await installAudioProbe(page);
  await installSoundOracle(page);
  expect(await page.evaluate(() => window.worldSoundProbe.context)).toBeNull();
  const supported = await page.evaluate(() => typeof AudioContext === 'function');
  await page.getByRole('button', { name: 'Enable original ambience' }).click();
  if (!supported) {
    expect(await page.evaluate(() => window.worldSoundProbe.starts)).toEqual([]);
    expect(await page.evaluate(() => window.worldSoundOracle.player?.decodedBytes)).toBe(0);
    await page.evaluate(() => window.worldSoundOracle.player?.destroy());
    await info.attach('audio-capability', {
      body: 'Unsupported Web Audio: no media request or playback.',
      contentType: 'text/plain',
    });
    return;
  }
  await expect
    .poll(() => page.evaluate(() => window.worldSoundProbe.rms()), { timeout: 10000 })
    .toBeGreaterThan(0.0001);
  await page.evaluate(() => window.worldSoundOracle.player?.select('mystic'));
  await expect.poll(() => page.evaluate(() => window.worldSoundProbe.starts.length)).toBe(2);
  const starts = await page.evaluate(() => window.worldSoundProbe.starts.length);
  await page.evaluate(() => window.worldSoundOracle.player?.setVolume(0));
  await expect.poll(() => page.evaluate(() => window.worldSoundProbe.rms())).toBeLessThan(0.000001);
  expect(await page.evaluate(() => window.worldSoundProbe.starts.length)).toBe(starts);
  await page.evaluate(() => window.worldSoundOracle.player?.setVolume(0.25));
  await expect
    .poll(() => page.evaluate(() => window.worldSoundProbe.outputLevels()))
    .toEqual([0.25]);
  await page.evaluate(() => window.worldSoundOracle.player?.select('arcade'));
  await expect.poll(() => page.evaluate(() => window.worldSoundProbe.starts.length)).toBe(3);
  await expect
    .poll(() => page.evaluate(() => window.worldSoundProbe.rms()))
    .toBeGreaterThan(0.0001);
  await page.evaluate(() => window.worldSoundOracle.player?.select(null));
  await expect
    .poll(() => page.evaluate(() => window.worldSoundProbe.active), { timeout: 5000 })
    .toBe(0);
  await page.evaluate(() => window.worldSoundOracle.player?.notify());
  await expect
    .poll(() =>
      page.evaluate(() => window.worldSoundProbe.starts.some(s => !s.loop && s.duration < 2))
    )
    .toBe(true);
  await page.evaluate(() => window.worldSoundOracle.player?.pause(true));
  await expect
    .poll(() => page.evaluate(() => window.worldSoundProbe.context?.state))
    .toBe('suspended');
  const count = await page.evaluate(() => window.worldSoundProbe.starts.length);
  await page.evaluate(() => window.worldSoundOracle.player?.notify());
  expect(await page.evaluate(() => window.worldSoundProbe.starts.length)).toBe(count);
  expect(await page.evaluate(() => window.worldSoundProbe.maximum)).toBeLessThanOrEqual(3);
  await page.evaluate(() => window.worldSoundOracle.player?.destroy());
  await expect
    .poll(() => page.evaluate(() => window.worldSoundProbe.context?.state))
    .toBe('closed');
});
