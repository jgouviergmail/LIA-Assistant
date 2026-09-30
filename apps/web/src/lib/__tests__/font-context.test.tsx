/**
 * FontProvider — the text size half: what it reads from storage, what it writes
 * on `<html>`, and what it refuses. The pre-paint script applies the same
 * stored value earlier (theme-init-script.tsx); the provider must agree with it
 * and keep it in step when the reader changes the size.
 */

import { act, renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import {
  DEFAULT_FONT_SIZE_PX,
  FONT_SIZE_CSS_VAR,
  FONT_SIZE_MAX_PX,
  FONT_SIZE_STORAGE_KEY,
} from '@/constants/fonts';
import { FontProvider, useFontFamily } from '../font-context';

const wrapper = ({ children }: { children: ReactNode }) => <FontProvider>{children}</FontProvider>;

const textScale = () => document.documentElement.style.getPropertyValue(FONT_SIZE_CSS_VAR);

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.style.removeProperty(FONT_SIZE_CSS_VAR);
});

describe('FontProvider — text size', () => {
  it('starts at the default and leaves the root untouched', () => {
    const { result } = renderHook(() => useFontFamily(), { wrapper });
    expect(result.current.fontSize).toBe(DEFAULT_FONT_SIZE_PX);
    expect(textScale()).toBe('');
  });

  it('adopts the stored size on mount', () => {
    window.localStorage.setItem(FONT_SIZE_STORAGE_KEY, '18');
    const { result } = renderHook(() => useFontFamily(), { wrapper });
    expect(result.current.fontSize).toBe(18);
    expect(textScale()).toBe('1.125');
  });

  it('ignores a stored size it does not offer', () => {
    window.localStorage.setItem(FONT_SIZE_STORAGE_KEY, '42');
    const { result } = renderHook(() => useFontFamily(), { wrapper });
    expect(result.current.fontSize).toBe(DEFAULT_FONT_SIZE_PX);
    expect(textScale()).toBe('');
  });

  it('applies and remembers a new size', () => {
    const { result } = renderHook(() => useFontFamily(), { wrapper });
    act(() => result.current.setFontSize(FONT_SIZE_MAX_PX));
    expect(result.current.fontSize).toBe(FONT_SIZE_MAX_PX);
    expect(textScale()).toBe('1.25');
    expect(window.localStorage.getItem(FONT_SIZE_STORAGE_KEY)).toBe(String(FONT_SIZE_MAX_PX));
  });

  it('clears the root rule when the default comes back', () => {
    window.localStorage.setItem(FONT_SIZE_STORAGE_KEY, '18');
    const { result } = renderHook(() => useFontFamily(), { wrapper });
    act(() => result.current.setFontSize(DEFAULT_FONT_SIZE_PX));
    expect(textScale()).toBe('');
    expect(window.localStorage.getItem(FONT_SIZE_STORAGE_KEY)).toBe(String(DEFAULT_FONT_SIZE_PX));
  });

  it('refuses a size outside the range instead of storing it', () => {
    const { result } = renderHook(() => useFontFamily(), { wrapper });
    act(() => result.current.setFontSize(99));
    expect(result.current.fontSize).toBe(DEFAULT_FONT_SIZE_PX);
    expect(window.localStorage.getItem(FONT_SIZE_STORAGE_KEY)).toBeNull();
  });

  it('survives localStorage throwing, which is what privacy modes do', () => {
    const original = Object.getOwnPropertyDescriptor(window, 'localStorage');
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      get() {
        throw new Error('access denied');
      },
    });
    try {
      const { result } = renderHook(() => useFontFamily(), { wrapper });
      act(() => result.current.setFontSize(FONT_SIZE_MAX_PX));
      // Not remembered, but still applied to this page.
      expect(result.current.fontSize).toBe(FONT_SIZE_MAX_PX);
      expect(textScale()).toBe('1.25');
    } finally {
      if (original) Object.defineProperty(window, 'localStorage', original);
    }
  });
});
