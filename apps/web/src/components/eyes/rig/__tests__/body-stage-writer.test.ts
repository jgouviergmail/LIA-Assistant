/** The real DOM writer must invalidate contact changes even with identical body axes. */
import { describe, expect, it, vi } from 'vitest';
import { createRigWriter } from '../apply';
import { restChannelValues } from '../channels';

function characterRoot() {
  const root = document.createElement('span');
  root.dataset.style = 'cozmo';
  root.dataset.volumeCharacter = 'bip';
  root.dataset.volumeVariant = 'female';
  return root;
}

function bodyPosition(root: HTMLElement) {
  return {
    x: parseFloat(root.style.getPropertyValue('--rig-body-x')),
    y: parseFloat(root.style.getPropertyValue('--rig-body-y')),
  };
}

describe('Supported body stage writer', () => {
  it('repaints a lift-off changing only support and restores contact without stale cached axes', () => {
    const root = characterRoot();
    const writer = createRigWriter(root);
    const values = { ...restChannelValues(), bodySx: 1.1, bodySy: 0.8 };
    writer.write(values);
    const planted = bodyPosition(root);
    expect(planted.y).toBeGreaterThan(0.2);
    writer.write({ ...values, bodySupport: 0 });
    expect(bodyPosition(root)).toEqual({ x: 0, y: 0 });
    writer.write(values);
    expect(bodyPosition(root)).toEqual(planted);
    writer.dispose();
  });

  it('moves the support to the other foot without requiring another roll or scale change', () => {
    const root = characterRoot();
    const writer = createRigWriter(root);
    const values = { ...restChannelValues(), bodySx: 1.1, bodySy: 0.9, bodyRoll: 8 };
    writer.write({ ...values, bodySupportSide: -1 });
    const left = bodyPosition(root);
    writer.write({ ...values, bodySupportSide: 1 });
    const right = bodyPosition(root);
    expect(left.x).not.toBe(right.x);
    expect(left.y).not.toBe(right.y);
    writer.dispose();
  });

  it('recalibrates support at a same-skin variant change', () => {
    const root = characterRoot();
    const writer = createRigWriter(root);
    const values = { ...restChannelValues(), bodySy: 0.8 };
    writer.write(values);
    const female = bodyPosition(root);
    root.dataset.volumeVariant = 'male';
    writer.write(values);
    expect(bodyPosition(root).y).toBeLessThan(female.y);
    root.dataset.volumeCharacter = 'orbit';
    writer.write(values);
    expect(bodyPosition(root)).toEqual({ x: 0, y: 0 });
    writer.dispose();
  });

  it('keeps the floor shadow on travel while the torso leans around its support', () => {
    const root = characterRoot();
    const writer = createRigWriter(root);
    const values = { ...restChannelValues(), bodyRoll: 10, bodySx: 1.02, bodySy: 0.95 };
    writer.write(values);
    expect(bodyPosition(root).x).toBeGreaterThan(0.1);
    expect(root.style.getPropertyValue('--rig-body-shadow-x')).toBe('0em');
    writer.write({ ...values, bodyX: 0.2, bodyShadowX: 0.2 });
    expect(root.style.getPropertyValue('--rig-body-shadow-x')).toBe('0.2em');
    writer.dispose();
  });

  it('retains the no-write cache, reset and terminal ownership contracts', () => {
    const root = characterRoot();
    const writer = createRigWriter(root);
    const values = { ...restChannelValues(), bodySy: 0.9 };
    writer.write(values);
    const property = vi.spyOn(root.style, 'setProperty');
    writer.write(values);
    expect(property).not.toHaveBeenCalled();
    writer.reset();
    writer.write(values);
    expect(property).toHaveBeenCalledWith('--rig-body-y', expect.any(String));
    property.mockClear();
    writer.dispose();
    writer.write({ ...values, bodySupportSide: 1 });
    expect(property).not.toHaveBeenCalled();
  });

  it('reprojects the supported stage when the viewport contracts', () => {
    const root = characterRoot();
    const writer = createRigWriter(root);
    const values = { ...restChannelValues(), bodySx: 1.1, bodySy: 0.8, bodyRoll: 8 };
    const box = { left: 200, top: 100, width: 78, height: 78, fontSize: 30 };
    writer.setBodyFrame(box, { left: 0, top: 0, width: 800, height: 600 });
    writer.write(values);
    const wide = bodyPosition(root);
    writer.setBodyFrame(box, { left: 230, top: 120, width: 90, height: 90 });
    writer.write(values);
    expect(bodyPosition(root)).not.toEqual(wide);
    writer.dispose();
  });
});
