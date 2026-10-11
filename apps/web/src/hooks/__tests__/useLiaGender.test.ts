/**
 * Unit tests for `useLiaGender`: reads/writes the `lia_gender` cookie and picks
 * the right LIA image variant from (gender × resolved theme). `next-themes` is
 * mocked so the resolved theme is deterministic.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { createElement } from 'react';
import { renderToString } from 'react-dom/server';

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
afterEach(() => {
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

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

  it.each(['unexpected', 'male=unexpected', 'MALE'])('ignores invalid cookie value %s', value => {
    document.cookie = `lia_gender=${value}; path=/`;
    const { result } = renderHook(() => useLiaGender());

    expect(result.current.isMale).toBe(false);
    expect(result.current.liaImage).toBe('/LIA_TC.jpg');
  });

  it('keeps a deterministic server snapshot before reading browser preferences', () => {
    document.cookie = 'lia_gender=male; path=/';
    mockUseTheme.mockReturnValue({ resolvedTheme: 'dark' });
    const snapshots: ReturnType<typeof useLiaGender>[] = [];
    function Snapshot() {
      snapshots.push(useLiaGender());
      return null;
    }

    renderToString(createElement(Snapshot));

    expect(snapshots[0]).toMatchObject({
      mounted: false,
      isMale: false,
      liaImage: '/LIA_TC.jpg',
      liaBackgroundImage: '/LIA_TC_BG.jpg',
      liaImageVariants: { female: '/LIA_TC.jpg', male: '/LIA_TCM.jpg' },
    });
  });
});

describe('useLiaGender — synchronized consumers', () => {
  it('updates an already-mounted consumer when another consumer chooses a variant', () => {
    mockUseTheme.mockReturnValue({ resolvedTheme: 'dark' });
    const dashboard = renderHook(() => useLiaGender());
    const companion = renderHook(() => useLiaGender());

    act(() => dashboard.result.current.setGender(true));

    expect(companion.result.current.isMale).toBe(true);
    expect(companion.result.current.liaImage).toBe('/LIA_TSM.jpg');
    expect(companion.result.current.liaBackgroundImage).toBe('/LIA_TSM_BG.jpg');

    act(() => companion.result.current.toggleGender());

    expect(dashboard.result.current.isMale).toBe(false);
    expect(dashboard.result.current.liaImage).toBe('/LIA_TS.jpg');
    expect(document.cookie).toContain('lia_gender=female');
  });

  it('keeps both consumers on an existing choice when it is selected repeatedly', () => {
    document.cookie = 'lia_gender=male; path=/';
    const dashboard = renderHook(() => useLiaGender());
    const companion = renderHook(() => useLiaGender());

    act(() => {
      dashboard.result.current.setGender(true);
      dashboard.result.current.setGender(true);
    });

    expect(dashboard.result.current.isMale).toBe(true);
    expect(companion.result.current.isMale).toBe(true);
    expect(document.cookie).toContain('lia_gender=male');

    act(() => companion.result.current.setGender(false));

    expect(dashboard.result.current.isMale).toBe(false);
    expect(companion.result.current.isMale).toBe(false);
  });

  it('rereads a cookie changed in another tab when the window regains focus', () => {
    const { result } = renderHook(() => useLiaGender());
    document.cookie = 'lia_gender=male; path=/';

    act(() => window.dispatchEvent(new Event('focus')));

    expect(result.current.isMale).toBe(true);
    expect(result.current.liaImage).toBe('/LIA_TCM.jpg');

    clearGenderCookie();
    act(() => window.dispatchEvent(new Event('focus')));

    expect(result.current.isMale).toBe(false);
    expect(result.current.liaImage).toBe('/LIA_TC.jpg');
  });

  it('restores the default on focus when the cookie has become invalid', () => {
    document.cookie = 'lia_gender=male; path=/';
    const { result } = renderHook(() => useLiaGender());
    document.cookie = 'lia_gender=male=unexpected; path=/';

    act(() => window.dispatchEvent(new Event('focus')));

    expect(result.current.isMale).toBe(false);
    expect(result.current.liaImage).toBe('/LIA_TC.jpg');
  });

  it('stops reading preference events after its consumer unmounts', () => {
    const { unmount } = renderHook(() => useLiaGender());
    unmount();
    const cookieRead = vi.spyOn(document, 'cookie', 'get');

    act(() => {
      window.dispatchEvent(new Event('lia-gender-change'));
      window.dispatchEvent(new Event('focus'));
    });

    expect(cookieRead).not.toHaveBeenCalled();
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

describe('useLiaGender — choosing a variant outright', () => {
  // The hero picker offers the two portraits side by side: the reader picks
  // one rather than flipping blind. Expressing that through `toggleGender`
  // would mean the caller comparing state before acting — a read-then-write
  // the hook can do correctly once.
  it('sets the requested variant and persists it', () => {
    const { result } = renderHook(() => useLiaGender());

    act(() => result.current.setGender(true));

    expect(result.current.isMale).toBe(true);
    expect(document.cookie).toContain('lia_gender=male');
    expect(result.current.liaImage).toBe('/LIA_TCM.jpg');
  });

  it('is idempotent — choosing the active variant changes nothing', () => {
    const { result } = renderHook(() => useLiaGender());

    act(() => result.current.setGender(false));

    expect(result.current.isMale).toBe(false);
    expect(document.cookie).toContain('lia_gender=female');
  });
});

describe('useLiaGender — the two portraits offered by the picker', () => {
  it('exposes both variants for the CURRENT theme', () => {
    const { result } = renderHook(() => useLiaGender());

    expect(result.current.liaImageVariants).toEqual({
      female: '/LIA_TC.jpg',
      male: '/LIA_TCM.jpg',
    });
  });

  it('follows the resolved theme, so the picker never shows a light face on a dark hero', () => {
    mockUseTheme.mockReturnValue({ resolvedTheme: 'dark' });
    const { result } = renderHook(() => useLiaGender());

    expect(result.current.liaImageVariants).toEqual({
      female: '/LIA_TS.jpg',
      male: '/LIA_TSM.jpg',
    });
  });
});
