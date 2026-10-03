/**
 * The cosmos pages' « pause the animations » state (WCAG 2.2.2): one attribute
 * on <html>, announced to every subscriber, remembered per viewer — and a
 * storage that refuses never breaks the page, it only forgets the choice.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  MOTION_EVENT,
  isMotionPaused,
  readStoredMotionPaused,
  restoreMotionPreference,
  setMotionPaused,
  subscribeMotion,
} from '../motion-pause';

afterEach(() => {
  vi.restoreAllMocks();
  delete document.documentElement.dataset.motion;
  window.localStorage.clear();
});

describe('motion pause', () => {
  it('pauses and resumes through one attribute on <html>, remembered for the viewer', () => {
    expect(isMotionPaused()).toBe(false);

    setMotionPaused(true);
    expect(document.documentElement.dataset.motion).toBe('paused');
    expect(isMotionPaused()).toBe(true);
    expect(readStoredMotionPaused()).toBe(true);

    setMotionPaused(false);
    expect(document.documentElement.dataset.motion).toBeUndefined();
    expect(readStoredMotionPaused()).toBe(false);
  });

  it('tells every subscriber, and stops telling one that left', () => {
    const heard = vi.fn();
    const leave = subscribeMotion(heard);

    setMotionPaused(true);
    expect(heard).toHaveBeenCalledTimes(1);

    leave();
    setMotionPaused(false);
    expect(heard).toHaveBeenCalledTimes(1);
  });

  it('applies the stored choice on a page load, and announces only a real change', () => {
    const heard = vi.fn();
    window.addEventListener(MOTION_EVENT, heard);
    try {
      restoreMotionPreference();
      expect(isMotionPaused()).toBe(false);
      expect(heard).not.toHaveBeenCalled();

      window.localStorage.setItem('lia_cosmos_motion_paused', '1');
      restoreMotionPreference();
      expect(isMotionPaused()).toBe(true);
      expect(heard).toHaveBeenCalledTimes(1);
    } finally {
      window.removeEventListener(MOTION_EVENT, heard);
    }
  });

  it('keeps working when the storage refuses: the choice holds for the page, unremembered', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });

    expect(readStoredMotionPaused()).toBe(false);
    expect(() => setMotionPaused(true)).not.toThrow();
    expect(isMotionPaused()).toBe(true);
  });
});
