/**
 * Unit tests for `useLiaGender`: reads/writes the `lia_gender` cookie and picks
 * the right LIA image variant from (gender × resolved theme). `next-themes` is
 * mocked so the resolved theme is deterministic.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';

const mockUseTheme = vi.hoisted(() => vi.fn(() => ({ resolvedTheme: 'light' })));
vi.mock('next-themes', () => ({ useTheme: mockUseTheme }));

import { useLiaGender } from '../useLiaGender';

function clearGenderCookie(): void {
  document.cookie = 'lia_gender=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
}

beforeEach(() => {
  clearGenderCookie();
  mockUseTheme.mockReturnValue({ resolvedTheme: 'light' });
});
afterEach(() => vi.clearAllMocks());

describe('useLiaGender — initial state', () => {
  it('defaults to female and light image, mounted after effect', () => {
    const { result } = renderHook(() => useLiaGender());
    expect(result.current.isMale).toBe(false);
    expect(result.current.mounted).toBe(true);
    expect(result.current.liaImage).toBe('/LIA_TC.jpg');
    expect(result.current.liaBackgroundImage).toBe('/LIA_TC_BG.jpg');
  });

  it('reads an existing male cookie', () => {
    document.cookie = 'lia_gender=male; path=/';
    const { result } = renderHook(() => useLiaGender());
    expect(result.current.isMale).toBe(true);
    expect(result.current.liaImage).toBe('/LIA_TCM.jpg');
  });
});

describe('useLiaGender — theme variants', () => {
  it('uses dark image variants when the resolved theme is dark', () => {
    mockUseTheme.mockReturnValue({ resolvedTheme: 'dark' });
    const { result } = renderHook(() => useLiaGender());
    expect(result.current.liaImage).toBe('/LIA_TS.jpg');
    expect(result.current.liaBackgroundImage).toBe('/LIA_TS_BG.jpg');
  });
});

describe('useLiaGender — toggle', () => {
  it('flips gender, persists the cookie, and swaps the image', () => {
    const { result } = renderHook(() => useLiaGender());

    act(() => result.current.toggleGender());

    expect(result.current.isMale).toBe(true);
    expect(document.cookie).toContain('lia_gender=male');
    expect(result.current.liaImage).toBe('/LIA_TCM.jpg');

    act(() => result.current.toggleGender());
    expect(result.current.isMale).toBe(false);
    expect(document.cookie).toContain('lia_gender=female');
  });
});
