/**
 * The sky's artwork: the vector drawings the owner chose on the bench (ADR-294,
 * follow-up of 2026-11-13), shipped as files the sheet installs only when the
 * rig announces their weather — never inline in the DOM, where every element of
 * a drawing would be restyled on each frame the rig writes.
 */
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const SKY_ART = [
  'cloud-fair',
  'cloud-rain',
  'cloud-snow',
  'drop',
  'sun-core',
  'sun-glow',
  'sun-rays',
] as const;

const directory = join(process.cwd(), 'public/avatars/sky/v1');
const sheet = readFileSync(join(process.cwd(), 'src/styles/eyes.css'), 'utf8').replace(
  /\/\*[\s\S]*?\*\//g,
  ''
);

describe('the sky artwork', () => {
  it('ships exactly the drawings the sky uses', () => {
    expect(readdirSync(directory).sort()).toEqual(SKY_ART.map(name => `${name}.svg`).sort());
  });

  it.each(SKY_ART)('%s is a still, self-contained vector drawing', name => {
    const text = readFileSync(join(directory, `${name}.svg`), 'utf8');
    expect(text.startsWith('<svg xmlns="http://www.w3.org/2000/svg"')).toBe(true);
    expect(text).toMatch(/viewBox="0 0 \d+ \d+"/);
    // No script, no handler, no link outside the drawing, no animation of its own:
    // the rig owns every motion (one clock), the sheet every placement.
    expect(text).not.toMatch(/<script|\son[a-z]+=|href=|<animate|<set\b|<style/i);
    expect(Buffer.byteLength(text)).toBeLessThanOrEqual(2 * 1024);
  });

  it('is installed by the sheet, each drawing behind the weather announced', () => {
    for (const name of SKY_ART) {
      const uses = [...sheet.matchAll(new RegExp(`url\\('/avatars/sky/v1/${name}\\.svg'\\)`, 'g'))];
      expect(uses.length, name).toBeGreaterThan(0);
    }
    const rules = [...sheet.matchAll(/([^{}]+)\{([^{}]*)\}/g)].filter(([, , block]) =>
      block.includes('/avatars/sky/v1/')
    );
    for (const [, selectors] of rules)
      for (const selector of selectors.split(','))
        expect(selector.trim(), selector).toMatch(/^\[data-weather-props~='[a-z]+'\] /);
  });
});
