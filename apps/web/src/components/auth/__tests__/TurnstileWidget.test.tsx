/**
 * TurnstileWidget — the bot check of a password door (ADR-364): it renders
 * Cloudflare's widget for THIS door, hands its token up, forgets an expired
 * one, says when the check could not load, starts over after a submit used the
 * token, and removes the widget when it leaves.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { act, renderWithProviders, screen } from '@/__tests__/test-utils';
import type { TurnstileApi, TurnstileRenderOptions } from '@/lib/turnstile';

const { loadTurnstile } = vi.hoisted(() => ({ loadTurnstile: vi.fn() }));
vi.mock('@/lib/turnstile', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/turnstile')>()),
  loadTurnstile,
}));

import { TurnstileWidget } from '../TurnstileWidget';

let rendered: TurnstileRenderOptions | null;
let api: TurnstileApi;

beforeEach(() => {
  rendered = null;
  api = {
    render: vi.fn((_container: HTMLElement, options: TurnstileRenderOptions) => {
      rendered = options;
      return 'widget-7';
    }),
    reset: vi.fn(),
    remove: vi.fn(),
  };
  loadTurnstile.mockReset();
  loadTurnstile.mockResolvedValue(api);
});

async function mount(resetSignal = 0, onToken = vi.fn(), onFailure = vi.fn()) {
  let view: ReturnType<typeof renderWithProviders> | undefined;
  await act(async () => {
    view = renderWithProviders(
      <TurnstileWidget
        siteKey="1x00000000000000000000AA"
        action="register"
        onToken={onToken}
        onFailure={onFailure}
        resetSignal={resetSignal}
      />
    );
  });
  if (!view) throw new Error('widget did not render');
  return { view, onToken, onFailure };
}

describe('TurnstileWidget', () => {
  it('is a named group the assistive technologies can announce', async () => {
    await mount();

    expect(screen.getByRole('group', { name: 'auth.turnstile.label' })).toBeInTheDocument();
  });

  it("renders Cloudflare's widget for this door, in the page's language", async () => {
    await mount();

    expect(api.render).toHaveBeenCalledTimes(1);
    expect(rendered).toMatchObject({
      sitekey: '1x00000000000000000000AA',
      action: 'register',
      language: 'fr',
      size: 'flexible',
      appearance: 'interaction-only',
    });
  });

  it('hands the token up, and forgets it once it expires', async () => {
    const { onToken, onFailure } = await mount();

    act(() => rendered?.callback('token-1'));
    expect(onToken).toHaveBeenLastCalledWith('token-1');

    act(() => rendered?.['expired-callback']());
    expect(onToken).toHaveBeenLastCalledWith(null);
    expect(onFailure).not.toHaveBeenCalled();
  });

  it('says so when the check cannot load', async () => {
    loadTurnstile.mockRejectedValue(new Error('blocked'));

    const { onToken, onFailure } = await mount();

    expect(screen.getByText('auth.turnstile.load_failed')).toBeInTheDocument();
    expect(onToken).toHaveBeenLastCalledWith(null);
    expect(onFailure).toHaveBeenCalled();
  });

  it('says so when the widget reports an error', async () => {
    const { onToken, onFailure } = await mount();

    act(() => {
      rendered?.['error-callback']();
    });

    expect(screen.getByText('auth.turnstile.load_failed')).toBeInTheDocument();
    expect(onToken).toHaveBeenLastCalledWith(null);
    expect(onFailure).toHaveBeenCalled();
  });

  it('tells the sign-in door it can still be sent when the check cannot load', async () => {
    loadTurnstile.mockRejectedValue(new Error('blocked'));

    await act(async () => {
      renderWithProviders(
        <TurnstileWidget
          siteKey="1x00000000000000000000AA"
          action="login"
          onToken={vi.fn()}
          onFailure={vi.fn()}
          resetSignal={0}
        />
      );
    });

    expect(screen.getByText('auth.turnstile.load_failed_sign_in')).toBeInTheDocument();
    expect(screen.queryByText('auth.turnstile.load_failed')).toBeNull();
  });

  it('starts over after a submit used the token', async () => {
    const onToken = vi.fn();
    const { view } = await mount(0, onToken);

    await act(async () => {
      view.rerender(
        <TurnstileWidget
          siteKey="1x00000000000000000000AA"
          action="register"
          onToken={onToken}
          onFailure={vi.fn()}
          resetSignal={1}
        />
      );
    });

    expect(api.reset).toHaveBeenCalledWith('widget-7');
    expect(onToken).toHaveBeenLastCalledWith(null);
  });

  it('removes the widget when it leaves the page', async () => {
    const { view } = await mount();

    view.unmount();

    expect(api.remove).toHaveBeenCalledWith('widget-7');
  });
});
