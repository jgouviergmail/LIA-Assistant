/**
 * ShareResponseMenu — the "…" menu at the end of an assistant bubble (UX P4):
 * native share where the platform offers it (feature detection, never
 * platform sniffing — desktop Chrome/Edge DO expose `navigator.share`), and a
 * dated `.md` export everywhere. A dismissed share sheet is a non-event; a
 * share that actually failed surfaces a toast.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { downloadMarkdown } = vi.hoisted(() => ({ downloadMarkdown: vi.fn() }));
vi.mock('@/lib/utils/download-markdown', () => ({ downloadMarkdown }));

const { toast } = vi.hoisted(() => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { ShareResponseMenu } from '../ShareResponseMenu';

const CONTENT = '# Été\n\nRéponse **markdown** à partager.';
// Local-time timestamp: the export name is stamped from the user's clock.
const TIMESTAMP = new Date(2026, 6, 28, 19, 42);

/** Installs (or removes) a `navigator.share` stub for one test. */
function stubNavigatorShare(impl: (() => Promise<void>) | undefined) {
  if (impl) {
    Object.defineProperty(navigator, 'share', { value: impl, configurable: true });
  } else {
    Reflect.deleteProperty(navigator, 'share');
  }
}

async function openMenu(user: ReturnType<typeof renderWithProviders>['user']) {
  await user.click(screen.getByRole('button', { name: 'chat.message.more_actions' }));
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  stubNavigatorShare(undefined);
});

describe('ShareResponseMenu — capability detection', () => {
  it('always offers the markdown export, and no share where the platform has none', async () => {
    const { user } = renderWithProviders(
      <ShareResponseMenu content={CONTENT} timestamp={TIMESTAMP} />
    );
    await openMenu(user);

    expect(screen.getByRole('menuitem', { name: 'chat.message.download_md' })).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: 'chat.message.share' })).toBeNull();
  });

  it('offers the native share when the platform exposes it', async () => {
    stubNavigatorShare(vi.fn(async () => {}));
    const { user } = renderWithProviders(
      <ShareResponseMenu content={CONTENT} timestamp={TIMESTAMP} />
    );
    await openMenu(user);

    expect(screen.getByRole('menuitem', { name: 'chat.message.share' })).toBeInTheDocument();
  });
});

describe('ShareResponseMenu — share', () => {
  it('hands the raw markdown to the platform share sheet', async () => {
    const share = vi.fn(async () => {});
    stubNavigatorShare(share);
    const { user } = renderWithProviders(
      <ShareResponseMenu content={CONTENT} timestamp={TIMESTAMP} />
    );
    await openMenu(user);
    await user.click(screen.getByRole('menuitem', { name: 'chat.message.share' }));

    expect(share).toHaveBeenCalledWith({ title: 'LIA', text: CONTENT });
  });

  it('treats a dismissed share sheet as a non-event', async () => {
    stubNavigatorShare(
      vi.fn(async () => {
        throw new DOMException('user cancelled', 'AbortError');
      })
    );
    const { user } = renderWithProviders(
      <ShareResponseMenu content={CONTENT} timestamp={TIMESTAMP} />
    );
    await openMenu(user);
    await user.click(screen.getByRole('menuitem', { name: 'chat.message.share' }));

    await waitFor(() => expect(toast.error).not.toHaveBeenCalled());
  });

  it('surfaces a share that actually failed', async () => {
    stubNavigatorShare(
      vi.fn(async () => {
        throw new Error('share broke');
      })
    );
    const { user } = renderWithProviders(
      <ShareResponseMenu content={CONTENT} timestamp={TIMESTAMP} />
    );
    await openMenu(user);
    await user.click(screen.getByRole('menuitem', { name: 'chat.message.share' }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('chat.message.share_error'));
  });
});

describe('ShareResponseMenu — markdown export', () => {
  it('exports the raw markdown under a dated lia-prefixed name', async () => {
    const { user } = renderWithProviders(
      <ShareResponseMenu content={CONTENT} timestamp={TIMESTAMP} />
    );
    await openMenu(user);
    await user.click(screen.getByRole('menuitem', { name: 'chat.message.download_md' }));

    expect(downloadMarkdown).toHaveBeenCalledWith(CONTENT, 'lia-2026-07-28-19-42');
  });

  it('zero-pads every date component', async () => {
    const { user } = renderWithProviders(
      // 3 Feb, 08:05 — every component below ten.
      <ShareResponseMenu content={CONTENT} timestamp={new Date(2026, 1, 3, 8, 5)} />
    );
    await openMenu(user);
    await user.click(screen.getByRole('menuitem', { name: 'chat.message.download_md' }));

    expect(downloadMarkdown).toHaveBeenCalledWith(CONTENT, 'lia-2026-02-03-08-05');
  });
});
