/**
 * FontSizeSettings — choosing the interface text size: the slider, the A−/A+
 * steps, the reset, the preview, persistence for an authenticated user (one
 * save in flight, the latest value wins, a failure rolled back and said), and
 * the note saying only the text changes size.
 *
 * `@/lib/font-context` is mocked so `setFontSize` is observable; the i18n stub
 * echoes interpolations so the value a label carries can be asserted.
 */

import { act, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { DEFAULT_FONT_SIZE_PX, FONT_SIZE_MAX_PX, FONT_SIZE_MIN_PX } from '@/constants/fonts';

vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts
        ? `${key}(${Object.entries(opts)
            .map(([k, v]) => `${k}=${String(v)}`)
            .join(',')})`
        : key,
    i18n: { language: 'fr' },
  }),
}));

const { setFontSize, fontState } = vi.hoisted(() => ({
  setFontSize: vi.fn(),
  fontState: { fontSize: 16 },
}));
vi.mock('@/lib/font-context', () => ({
  FontProvider: ({ children }: { children: React.ReactNode }) => children,
  useFontFamily: () => ({
    fontFamily: 'system',
    setFontFamily: vi.fn(),
    fontSize: fontState.fontSize,
    setFontSize,
  }),
}));

const { useAuth, refreshUser } = vi.hoisted(() => ({ useAuth: vi.fn(), refreshUser: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));

const { mutate } = vi.hoisted(() => ({ mutate: vi.fn() }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation: () => ({ mutate }) }));

const { toast } = vi.hoisted(() => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { FontSizeSettings } from '../FontSizeSettings';

const percent = (px: number) =>
  new Intl.NumberFormat('fr', { style: 'percent', maximumFractionDigits: 0 }).format(px / 16);
const valueText = (px: number) => `settings.font_size.value(px=${px},percent=${percent(px)})`;

const slider = () => screen.getByRole('slider', { name: 'settings.font_size.slider_label' });
const decrease = () => screen.getByRole('button', { name: 'settings.font_size.decrease' });
const increase = () => screen.getByRole('button', { name: 'settings.font_size.increase' });
const preview = () => screen.getByTestId('font-size-preview');

type TestAccount = { id: string; font_size?: number } | null;

function renderAt(size: number, user: TestAccount = { id: 'u1', font_size: size }) {
  fontState.fontSize = size;
  useAuth.mockReturnValue({ user, refreshUser });
  return renderWithProviders(<FontSizeSettings lng="fr" />);
}

/** A save the test settles by hand, to observe what happens while it is in flight. */
function deferredSave() {
  let settle: () => void = () => {};
  let fail: (error: Error) => void = () => {};
  const promise = new Promise<undefined>((resolve, reject) => {
    settle = () => resolve(undefined);
    fail = reject;
  });
  return { promise, settle, fail };
}

beforeEach(() => {
  vi.clearAllMocks();
  mutate.mockResolvedValue(undefined);
  refreshUser.mockResolvedValue(undefined);
});

describe('FontSizeSettings', () => {
  it('announces the current size in px and in percent', () => {
    renderAt(18);
    expect(slider()).toHaveAttribute('aria-valuenow', '18');
    expect(slider()).toHaveAttribute('aria-valuetext', valueText(18));
    // Verbatim: French puts a narrow no-break space before %, which the
    // default normalizer would fold into a plain space.
    expect(screen.getByText(valueText(18), { normalizer: text => text })).toBeInTheDocument();
  });

  it('offers exactly the supported range', () => {
    renderAt(DEFAULT_FONT_SIZE_PX);
    expect(slider()).toHaveAttribute('aria-valuemin', String(FONT_SIZE_MIN_PX));
    expect(slider()).toHaveAttribute('aria-valuemax', String(FONT_SIZE_MAX_PX));
  });

  it('marks the default size and offers no reset there', () => {
    renderAt(DEFAULT_FONT_SIZE_PX);
    expect(screen.getByText('settings.font_size.default_badge')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'settings.font_size.reset' })
    ).not.toBeInTheDocument();
  });

  it('A+ applies and saves the next step, then re-reads the account once', async () => {
    const { user } = renderAt(DEFAULT_FONT_SIZE_PX);
    await user.click(increase());
    expect(setFontSize).toHaveBeenCalledWith(17);
    await waitFor(() => expect(mutate).toHaveBeenCalledWith('/users/u1', { font_size: 17 }));
    await waitFor(() => expect(refreshUser).toHaveBeenCalledTimes(1));
  });

  it('A− applies and saves the previous step', async () => {
    const { user } = renderAt(DEFAULT_FONT_SIZE_PX);
    await user.click(decrease());
    expect(setFontSize).toHaveBeenCalledWith(15);
    await waitFor(() => expect(mutate).toHaveBeenCalledWith('/users/u1', { font_size: 15 }));
  });

  it('keeps the focus on a step button that reaches its bound', async () => {
    // `disabled` on the focused control would blur it back to <body>
    // (apps/web/CLAUDE.md): the bound is aria-disabled and guarded instead.
    const { user, rerender } = renderAt(19);
    increase().focus();
    await user.keyboard('{Enter}');
    expect(setFontSize).toHaveBeenCalledExactlyOnceWith(20);

    fontState.fontSize = 20;
    rerender(<FontSizeSettings lng="fr" />);
    expect(increase()).toHaveFocus();
    expect(increase()).toHaveAttribute('aria-disabled', 'true');
    expect(increase()).toBeEnabled();

    await user.keyboard('{Enter}');
    expect(setFontSize).toHaveBeenCalledTimes(1);
  });

  it('marks A− at the minimum and A+ at the maximum as unavailable', () => {
    const { unmount } = renderAt(FONT_SIZE_MIN_PX);
    expect(decrease()).toHaveAttribute('aria-disabled', 'true');
    expect(increase()).toHaveAttribute('aria-disabled', 'false');
    unmount();
    renderAt(FONT_SIZE_MAX_PX);
    expect(increase()).toHaveAttribute('aria-disabled', 'true');
    expect(decrease()).toHaveAttribute('aria-disabled', 'false');
  });

  it('the keyboard moves the slider one step and commits it', async () => {
    renderAt(DEFAULT_FONT_SIZE_PX);
    slider().focus();
    fireEvent.keyDown(slider(), { key: 'ArrowRight' });
    expect(setFontSize).toHaveBeenCalledWith(17);
    await waitFor(() => expect(mutate).toHaveBeenCalledWith('/users/u1', { font_size: 17 }));
  });

  it('follows a size changed elsewhere after a keyboard commit', () => {
    // Radix commits BEFORE it reports the change, so a naive draft outlived
    // the commit and froze the slider on its value (review 2026-09-29).
    const { rerender } = renderAt(DEFAULT_FONT_SIZE_PX);
    slider().focus();
    fireEvent.keyDown(slider(), { key: 'ArrowRight' });
    fontState.fontSize = 17;
    rerender(<FontSizeSettings lng="fr" />);

    fontState.fontSize = 19;
    rerender(<FontSizeSettings lng="fr" />);
    expect(slider()).toHaveAttribute('aria-valuenow', '19');
  });

  it('keeps one save in flight and sends only the latest size after it', async () => {
    const first = deferredSave();
    mutate.mockReturnValueOnce(first.promise);
    const { user, rerender } = renderAt(DEFAULT_FONT_SIZE_PX);

    await user.click(increase());
    fontState.fontSize = 17;
    rerender(<FontSizeSettings lng="fr" />);
    await user.click(increase());
    fontState.fontSize = 18;
    rerender(<FontSizeSettings lng="fr" />);
    await user.click(increase());

    // Only the first save left; the two others wait, and only the last counts.
    expect(mutate).toHaveBeenCalledTimes(1);
    await act(async () => first.settle());
    await waitFor(() => expect(mutate).toHaveBeenCalledTimes(2));
    expect(mutate).toHaveBeenLastCalledWith('/users/u1', { font_size: 19 });
    // The account is re-read once, after the last save: an echo of 17 would
    // have shrunk the page back under the reader.
    await waitFor(() => expect(refreshUser).toHaveBeenCalledTimes(1));
  });

  it('rolls a failed save back to the account size and says so', async () => {
    const save = deferredSave();
    mutate.mockReturnValueOnce(save.promise);
    const { user } = renderAt(DEFAULT_FONT_SIZE_PX);

    await user.click(increase());
    expect(setFontSize).toHaveBeenLastCalledWith(17);
    await act(async () => save.fail(new Error('network')));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('settings.font_size.save_error'));
    expect(setFontSize).toHaveBeenLastCalledWith(DEFAULT_FONT_SIZE_PX);
    expect(refreshUser).not.toHaveBeenCalled();
  });

  it('the reset brings the default back', async () => {
    const { user } = renderAt(19);
    await user.click(screen.getByRole('button', { name: 'settings.font_size.reset' }));
    expect(setFontSize).toHaveBeenCalledWith(DEFAULT_FONT_SIZE_PX);
    await waitFor(() =>
      expect(mutate).toHaveBeenCalledWith('/users/u1', { font_size: DEFAULT_FONT_SIZE_PX })
    );
  });

  it('draws the preview text at the chosen size', () => {
    renderAt(20);
    expect(preview()).toHaveStyle({ fontSize: '20px' });
    expect(screen.getByText('settings.font_size.preview_question')).toBeInTheDocument();
    expect(screen.getByText('settings.font_size.preview_answer')).toBeInTheDocument();
  });

  it('applies locally without saving for a visitor', async () => {
    const { user } = renderAt(DEFAULT_FONT_SIZE_PX, null);
    await user.click(increase());
    expect(setFontSize).toHaveBeenCalledWith(17);
    expect(mutate).not.toHaveBeenCalled();
  });

  it('says what the size changes, and that it follows the account', () => {
    renderAt(DEFAULT_FONT_SIZE_PX);
    expect(screen.getByText('settings.font_size.info_note')).toBeInTheDocument();
  });
});
