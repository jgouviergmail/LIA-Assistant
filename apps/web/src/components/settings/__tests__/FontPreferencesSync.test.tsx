/**
 * FontPreferencesSync — the account's font family and text size reach the
 * page on EVERY authenticated screen, not only when Settings is open. Before
 * it, a preference saved on one device was applied on another only after the
 * reader happened to visit the font section there.
 */

import { render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { setFontFamily, setFontSize, fontState } = vi.hoisted(() => ({
  setFontFamily: vi.fn(),
  setFontSize: vi.fn(),
  fontState: { fontFamily: 'system', fontSize: 16 },
}));
vi.mock('@/lib/font-context', () => ({
  useFontFamily: () => ({ ...fontState, setFontFamily, setFontSize }),
}));

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));

import { FontPreferencesSync } from '../FontPreferencesSync';

beforeEach(() => {
  vi.clearAllMocks();
  fontState.fontFamily = 'system';
  fontState.fontSize = 16;
});

describe('FontPreferencesSync', () => {
  it('applies the account text size', () => {
    useAuth.mockReturnValue({ user: { id: 'u1', font_size: 18 } });
    render(<FontPreferencesSync />);
    expect(setFontSize).toHaveBeenCalledWith(18);
  });

  it('applies the account font family', () => {
    useAuth.mockReturnValue({ user: { id: 'u1', font_family: 'geist' } });
    render(<FontPreferencesSync />);
    expect(setFontFamily).toHaveBeenCalledWith('geist');
  });

  it('leaves the page alone when the account already agrees', () => {
    useAuth.mockReturnValue({
      user: { id: 'u1', font_family: 'system', font_size: 16 },
    });
    render(<FontPreferencesSync />);
    expect(setFontFamily).not.toHaveBeenCalled();
    expect(setFontSize).not.toHaveBeenCalled();
  });

  it('never undoes a local choice the save has not echoed back yet', () => {
    useAuth.mockReturnValue({ user: { id: 'u1', font_size: 16 } });
    const { rerender } = render(<FontPreferencesSync />);
    // The reader picks 18: applied locally, the PATCH still in flight.
    fontState.fontSize = 18;
    rerender(<FontPreferencesSync />);
    expect(setFontSize).not.toHaveBeenCalled();
    // The refreshed account then carries another device's choice.
    useAuth.mockReturnValue({ user: { id: 'u1', font_size: 19 } });
    rerender(<FontPreferencesSync />);
    expect(setFontSize).toHaveBeenCalledExactlyOnceWith(19);
  });

  it('ignores values it does not offer', () => {
    useAuth.mockReturnValue({
      user: { id: 'u1', font_family: 'comic-sans', font_size: 42 },
    });
    render(<FontPreferencesSync />);
    expect(setFontFamily).not.toHaveBeenCalled();
    expect(setFontSize).not.toHaveBeenCalled();
  });

  it('keeps the device choice for a visitor', () => {
    useAuth.mockReturnValue({ user: null });
    render(<FontPreferencesSync />);
    expect(setFontFamily).not.toHaveBeenCalled();
    expect(setFontSize).not.toHaveBeenCalled();
  });

  it('renders nothing', () => {
    useAuth.mockReturnValue({ user: null });
    const { container } = render(<FontPreferencesSync />);
    expect(container).toBeEmptyDOMElement();
  });
});
