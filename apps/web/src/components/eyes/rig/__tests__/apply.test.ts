/**
 * The DOM writer — correctness first, then the two filters that keep a
 * permanently-on-screen widget cheap.
 */

import { describe, it, expect, vi } from 'vitest';
import { createRigWriter } from '@/components/eyes/rig/apply';
import { CHANNEL_KEYS, restChannelValues } from '@/components/eyes/rig/channels';

function host(): HTMLElement {
  const element = document.createElement('span');
  document.body.appendChild(element);
  return element;
}

describe('createRigWriter', () => {
  it('writes every channel onto the element as a `--rig-*` property', () => {
    const element = host();
    createRigWriter(element).write(restChannelValues());
    expect(element.style.getPropertyValue('--rig-sy-l')).toBe('1');
    expect(element.style.getPropertyValue('--rig-lid-top-r')).toBe('0%');
    expect(element.style.getPropertyValue('--rig-r-top-l')).toBe('0.28em');
    // Everything the table declares actually lands.
    CHANNEL_KEYS.forEach(key =>
      expect(element.style.getPropertyValue(`--rig-${key}`)).toBeDefined()
    );
  });

  it('serializes a pose with its units', () => {
    const element = host();
    createRigWriter(element).write({ ...restChannelValues(), syL: 0.55, rotL: 7, lidTopL: 34 });
    expect(element.style.getPropertyValue('--rig-sy-l')).toBe('0.55');
    expect(element.style.getPropertyValue('--rig-rot-l')).toBe('7deg');
    expect(element.style.getPropertyValue('--rig-lid-top-l')).toBe('34%');
  });

  it('writes nothing at all on an unchanged frame', () => {
    const element = host();
    const writer = createRigWriter(element);
    const values = restChannelValues();
    writer.write(values);
    const spy = vi.spyOn(element.style, 'setProperty');
    writer.write(values);
    expect(spy).not.toHaveBeenCalled();
  });

  it('ignores a move too small to change the displayed value', () => {
    const element = host();
    const writer = createRigWriter(element);
    const values = restChannelValues();
    writer.write(values);
    const spy = vi.spyOn(element.style, 'setProperty');
    // `mass` keeps 4 decimals: 1e-6 cannot alter its text.
    writer.write({ ...values, mass: 1 + 1e-6 });
    expect(spy).not.toHaveBeenCalled();
    writer.write({ ...values, mass: 1.05 });
    expect(spy).toHaveBeenCalledWith('--rig-mass', '1.05');
  });

  it('re-emits everything after a reset (a remount must not inherit a cache)', () => {
    const element = host();
    const writer = createRigWriter(element);
    const values = restChannelValues();
    writer.write(values);
    writer.reset();
    const spy = vi.spyOn(element.style, 'setProperty');
    writer.write(values);
    expect(spy).toHaveBeenCalledTimes(CHANNEL_KEYS.length);
  });
});
