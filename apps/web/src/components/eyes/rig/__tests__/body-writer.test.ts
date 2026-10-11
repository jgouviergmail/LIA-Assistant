import { describe, expect, it, vi } from 'vitest';
import { createRigWriter } from '../apply';
import { restChannelValues } from '../channels';

describe('whole-body paint boundary', () => {
  it('bounds temporary paint without changing the anchor and never publishes the unbounded request', () => {
    const element = document.createElement('span');
    element.style.left = '25%';
    const writer = createRigWriter(element);
    writer.setBodyFrame(
      { left: 80, top: 50, width: 52, height: 52, fontSize: 20 },
      { left: 0, top: 0, width: 320, height: 400 }
    );
    const spy = vi.spyOn(element.style, 'setProperty');
    writer.write({ ...restChannelValues(), bodyX: 100, bodyY: -100, bodyRoll: 45 });
    const x = parseFloat(element.style.getPropertyValue('--rig-body-x'));
    const y = parseFloat(element.style.getPropertyValue('--rig-body-y'));
    expect(x).toBeGreaterThan(0);
    expect(x).toBeLessThan(9);
    expect(y).toBeGreaterThan(-2);
    expect(element.style.left).toBe('25%');
    expect(spy.mock.calls.filter(([key]) => key === '--rig-body-x')).toHaveLength(1);
    expect(element.dataset.bodyMoving).toBe('true');
  });

  it('reprojects on a viewport change, caches quiet frames, and restores identity at home', () => {
    const element = document.createElement('span');
    const writer = createRigWriter(element);
    const box = { left: 80, top: 50, width: 52, height: 52, fontSize: 20 };
    writer.setBodyFrame(box, { left: 0, top: 0, width: 600, height: 400 });
    const values = { ...restChannelValues(), bodyX: 10 };
    writer.write(values);
    const before = element.style.getPropertyValue('--rig-body-x');
    const spy = vi.spyOn(element.style, 'setProperty');
    writer.write(values);
    expect(spy).not.toHaveBeenCalled();
    writer.setBodyFrame(box, { left: 0, top: 0, width: 200, height: 400 });
    writer.write(values);
    expect(element.style.getPropertyValue('--rig-body-x')).not.toBe(before);
    writer.write(restChannelValues());
    expect(element.style.getPropertyValue('--rig-body-x')).toBe('0em');
    expect(element.style.getPropertyValue('--rig-body-y')).toBe('0em');
    expect(element.style.getPropertyValue('--rig-body-roll')).toBe('0deg');
    expect(element.style.getPropertyValue('--rig-body-sx')).toBe('1');
    expect(element.dataset.bodyMoving).toBe('false');
    writer.dispose();
    spy.mockClear();
    writer.write(values);
    expect(spy).not.toHaveBeenCalled();
  });
});
