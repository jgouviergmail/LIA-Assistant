/**
 * ShareResponseMenu — the "…" menu at the end of an assistant bubble (UX P4):
 * native share where the platform offers it (feature detection, never
 * platform sniffing — desktop Chrome/Edge DO expose `navigator.share`), and a
 * dated `.md` export everywhere. A dismissed share sheet is a non-event; a
 * share that actually failed surfaces a toast.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { downloadMarkdown } = vi.hoisted(() => ({ downloadMarkdown: vi.fn() }));
vi.mock('@/lib/utils/download-markdown', () => ({ downloadMarkdown }));

const { toast } = vi.hoisted(() => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

// Spied rather than stubbed away: which connections the menu offers — and
// which it refuses — is the property under test.
const { usePeerRecipients } = vi.hoisted(() => ({
  // `unknown[]` rather than an inferred `never[]`: the tests below feed it
  // real connection rows, and an empty-array default would type them away.
  usePeerRecipients: vi.fn((): unknown[] => []),
}));
vi.mock('@/hooks/usePeerRecipients', () => ({ usePeerRecipients }));

import { ShareResponseMenu } from '../ShareResponseMenu';
import type { ConnectionView } from '@/hooks/usePeerConnections';

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

describe('sharing an answer with a connected peer', () => {
  // Relaying is NOT a browser capability: `send_peer_message` returns a draft
  // the user must confirm, and delivery is assistant-to-assistant. This menu
  // therefore PREFILLS the composer with the request — the same road a typed
  // sentence takes, HITL confirmation included. Posting the relay from here
  // would bypass that, and the capability channel is read-only by design.
  type PeerRow = Pick<ConnectionView, 'id' | 'peer_display_name' | 'status'>;

  const CONNECTIONS: PeerRow[] = [
    { id: 'c1', peer_display_name: 'Gérard Dupont', status: 'accepted' },
    { id: 'c2', peer_display_name: 'Claire Lefèvre', status: 'accepted' },
    { id: 'c3', peer_display_name: 'Paul Pending', status: 'pending' },
  ];

  function renderMenu(
    over: { connections?: PeerRow[]; onPrefillComposer?: (text: string) => void; prefill?: boolean } = {}
  ) {
    // The hook already returns ACCEPTED only; the pending row below proves
    // the FILTER lives there and not in the menu.
    usePeerRecipients.mockReturnValue(
      (over.connections ?? CONNECTIONS).filter(c => c.status === 'accepted')
    );
    // A composer is the ordinary case; `prefill: false` is how the
    // no-composer surface is expressed, so the other cases do not have to
    // thread a callback they never inspect.
    const onPrefillComposer =
      over.prefill === false ? undefined : (over.onPrefillComposer ?? vi.fn());
    return renderWithProviders(
      <ShareResponseMenu
        content="Voici la synthèse."
        timestamp={new Date('2026-08-03T10:00:00Z')}
        onPrefillComposer={onPrefillComposer}
      />
    );
  }

  it('offers the action once the account has a connection', async () => {
    const { user } = renderMenu();

    await user.click(screen.getByRole('button', { name: 'chat.message.more_actions' }));

    expect(await screen.findByText('chat.message.share_peer')).toBeInTheDocument();
  });

  it('lists only ACCEPTED connections — a pending one cannot receive anything', async () => {
    const { user } = renderMenu();

    await user.click(screen.getByRole('button', { name: 'chat.message.more_actions' }));
    expect(await screen.findByText('Gérard Dupont')).toBeInTheDocument();
    expect(screen.getByText('Claire Lefèvre')).toBeInTheDocument();
    expect(screen.queryByText('Paul Pending')).not.toBeInTheDocument();
  });

  it('prefills the composer with the recipient and the content, and sends nothing', async () => {
    const onPrefillComposer = vi.fn();
    const { user } = renderMenu({ onPrefillComposer });

    await user.click(screen.getByRole('button', { name: 'chat.message.more_actions' }));
    // By ROLE: the recipients are menu items, and picking one is what a
    // keyboard user does too.
    await user.click(await screen.findByRole('menuitem', { name: 'Gérard Dupont' }));

    // Prefilled, never posted: nothing here calls the peer API. The request
    // takes the ordinary road — agent, `send_peer_message`, HITL confirmation.
    expect(onPrefillComposer).toHaveBeenCalledTimes(1);
    expect(onPrefillComposer).toHaveBeenCalledWith('chat.message.share_peer_draft');
  });

  it('builds that draft from the recipient AND the answer', () => {
    // The harness translator is `(key) => key` (src/__tests__/setup.ts), so
    // the interpolated sentence cannot be observed through the DOM. What IS
    // observable — and what a refactor could silently drop — is that the
    // wording declares both placeholders in every locale it ships in.
    const locales = ['en', 'fr', 'de', 'es', 'it', 'zh'];
    for (const lng of locales) {
      // Read from disk rather than `require`: the repo forbids CJS imports,
      // and a static `import` of six JSON files would pull them into the
      // bundle graph of a unit test.
      const raw = readFileSync(
        join(process.cwd(), 'locales', lng, 'translation.json'),
        'utf-8'
      );
      const wording = (JSON.parse(raw) as { chat: { message: Record<string, string> } }).chat
        .message.share_peer_draft;
      expect(wording, `${lng} must name the recipient`).toContain('{{recipient}}');
      expect(wording, `${lng} must carry the answer`).toContain('{{content}}');
    }
  });

  it('hides the action entirely when nobody is connected', async () => {
    const { user } = renderMenu({ connections: [] });

    await user.click(screen.getByRole('button', { name: 'chat.message.more_actions' }));

    // An entry that opens an empty list is a dead end, not a discovery.
    expect(screen.queryByText('chat.message.share_peer')).not.toBeInTheDocument();
  });

  it('hides it when the caller cannot prefill anything', async () => {
    const { user } = renderMenu({ prefill: false });

    await user.click(screen.getByRole('button', { name: 'chat.message.more_actions' }));

    expect(screen.queryByText('chat.message.share_peer')).not.toBeInTheDocument();
  });
});
