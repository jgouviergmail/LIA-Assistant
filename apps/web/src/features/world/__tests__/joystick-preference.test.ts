import { createElement } from 'react';
import { renderToString } from 'react-dom/server';
import { act, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import {
  isJoystickPreference,
  shouldShowJoystick,
  useJoystickPreference,
} from '../useJoystickPreference';

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});
it('accepts only finite device preferences and restores the chosen visibility', () => {
  for (const value of [null, '', 'yes', {}, 1]) expect(isJoystickPreference(value)).toBe(false);
  localStorage.setItem('lia-world-joystick', 'show');
  const { result } = renderHook(useJoystickPreference);
  expect(result.current[0]).toBe('show');
  act(() => result.current[1]('hide'));
  expect(localStorage.getItem('lia-world-joystick')).toBe('hide');
});
it('survives denied storage without disabling session controls', () => {
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
    throw new Error('denied');
  });
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
    throw new Error('denied');
  });
  const { result } = renderHook(useJoystickPreference);
  expect(result.current[0]).toBe('auto');
  act(() => result.current[1]('show'));
  expect(result.current[0]).toBe('show');
});

it('ignores an obsolete stored value', () => {
  localStorage.setItem('lia-world-joystick', 'obsolete');
  expect(renderHook(useJoystickPreference).result.current[0]).toBe('auto');
});

it('hydrates from a neutral server preference and synchronizes device storage events', () => {
  localStorage.setItem('lia-world-joystick', 'show');
  function Preference() {
    return createElement('span', null, useJoystickPreference()[0]);
  }
  expect(renderToString(createElement(Preference))).toBe('<span>auto</span>');
  const { result } = renderHook(useJoystickPreference);
  expect(result.current[0]).toBe('show');
  act(() => {
    localStorage.setItem('lia-world-joystick', 'hide');
    window.dispatchEvent(new StorageEvent('storage', { key: 'lia-world-joystick' }));
  });
  expect(result.current[0]).toBe('hide');
});

it.each([
  ['show', false, false, true],
  ['hide', true, false, false],
  ['auto', false, false, false],
  ['auto', true, false, true],
  ['show', true, true, false],
] as const)(
  'honors device choice %s and the panel input fence',
  (preference, touch, paused, expected) => {
    expect(shouldShowJoystick(preference, touch, paused)).toBe(expected);
  }
);
