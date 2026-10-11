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
  it('refreshes added mouth layers at a material switch, then avoids querying them on stable frames', () => {
    const element = host();
    element.dataset.style = 'billes';
    element.innerHTML = '<svg><path data-rig-mouth=""/></svg>';
    const writer = createRigWriter(element);
    const values = restChannelValues();
    writer.write(values);
    const mouth = element.querySelector<SVGPathElement>('[data-rig-mouth]')!;
    mouth.dataset.rigMouthShape = 'sculpted';
    mouth.parentElement!.insertAdjacentHTML(
      'beforeend',
      '<path data-rig-mouth-teeth=""/><path data-rig-mouth-tongue=""/>'
    );
    const teeth = element.querySelector('[data-rig-mouth-teeth]')!;
    const tongue = element.querySelector('[data-rig-mouth-tongue]')!;
    writer.write(values);
    expect(teeth.getAttribute('d')).toBeTruthy();
    expect(tongue.getAttribute('d')).toBeTruthy();
    const queries = vi.spyOn(element, 'querySelector');
    const firstTeeth = teeth.getAttribute('d');
    writer.write({ ...values, mouthOpen: 0.7, mouthCurve: 0.7 });
    expect(teeth.getAttribute('d')).not.toBe(firstTeeth);
    writer.write(values);
    expect(queries).not.toHaveBeenCalled();
    delete mouth.dataset.rigMouthShape;
    teeth.remove();
    tongue.remove();
    writer.write(values);
    queries.mockClear();
    writer.write({ ...values, mouthOpen: 0.4 });
    expect(queries).not.toHaveBeenCalled();
  });

  it('projects continuous SVG contours and does not rewrite an unchanged eye when the mouth moves', () => {
    const element = host();
    element.dataset.style = 'anneaux';
    element.innerHTML =
      '<svg><path data-rig-mouth=""/><path data-rig-brow="L"/><path data-rig-brow="R"/><path data-rig-stroke="L"/><path data-rig-ring="L"/><path data-rig-stroke="R"/><path data-rig-ring="R"/></svg>';
    const eye = element.querySelector('[data-rig-stroke="L"]')!;
    const mouth = element.querySelector('[data-rig-mouth]')!;
    const writer = createRigWriter(element);
    const values = { ...restChannelValues(), strokeRoundL: 1, strokeRoundR: 1 };
    writer.write(values);
    const before = mouth.getAttribute('d');
    const writes = vi.spyOn(eye, 'setAttribute');
    writer.write({ ...values, mouthCurve: 0.7 });
    expect(mouth.getAttribute('d')).not.toBe(before);
    expect(writes).not.toHaveBeenCalled();
    writer.write({ ...values, strokeArcL: 1, strokeWeightL: 12 });
    expect(writes).toHaveBeenCalledWith('stroke-width', '12');
    expect(element.querySelector('[data-rig-ring="L"]')?.getAttribute('opacity')).toBe('0');
    writer.reset();
    writer.write(values);
    expect(element.querySelector('[data-rig-ring="L"]')?.getAttribute('opacity')).toBe('1');
  });
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
