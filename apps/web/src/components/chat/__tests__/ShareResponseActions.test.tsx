/**
 * ShareResponseActions — « Share » and « Download » under an assistant bubble.
 *
 * They replaced a « … » menu that hid both (owner request, 2026-09-24):
 *
 * - Download is ONE click: the dated `.md` export, everywhere.
 * - Share is one click too when the platform share sheet is the only way out
 *   (feature detection, never platform sniffing — desktop Chrome/Edge DO expose
 *   `navigator.share`). It opens a menu when a connection can also receive the
 *   answer: the composer is PREFILLED, so the relay takes the ordinary road,
 *   HITL confirmation included.
 * - The connections are read only while that menu is open (a closed menu on
 *   twenty bubbles must cost nothing), and the menu tells « loading », « could
 *   not be read » and « none yet » apart.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import type { ConnectionView } from '@/hooks/usePeerConnections';
import type { PeerRecipientsState } from '@/hooks/usePeerRecipients';
import { PeersAvailabilityProvider } from '@/lib/peers/availability-context';

const { downloadMarkdown } = vi.hoisted(() => ({ downloadMarkdown: vi.fn() }));
vi.mock('@/lib/utils/download-markdown', () => ({ downloadMarkdown }));

const { toast } = vi.hoisted(() => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

// Spied rather than stubbed away: WHEN the connections are read, and what the
// menu says about each state, are properties under test.
const { usePeerRecipientsState } = vi.hoisted(() => ({
  usePeerRecipientsState: vi.fn(
    (_enabled: boolean): PeerRecipientsState => ({ recipients: [], loading: false, error: null })
  ),
}));
vi.mock('@/hooks/usePeerRecipients', () => ({ usePeerRecipientsState }));

import { ShareResponseActions } from '../ShareResponseActions';

const CONTENT = '# Été\n\nRéponse **markdown** à partager.';
// Local-time timestamp: the export name is stamped from the user's clock.
const TIMESTAMP = new Date(2026, 6, 28, 19, 42);

type PeerRow = Pick<ConnectionView, 'id' | 'peer_display_name' | 'status'>;
const CONNECTIONS: PeerRow[] = [
  { id: 'c1', peer_display_name: 'Gérard Dupont', status: 'accepted' },
  { id: 'c2', peer_display_name: 'Claire Lefèvre', status: 'accepted' },
];

/** Installs (or removes) a `navigator.share` stub for one test. */
function stubNavigatorShare(impl: (() => Promise<void>) | undefined) {
  if (impl) {
    Object.defineProperty(navigator, 'share', { value: impl, configurable: true });
  } else {
    Reflect.deleteProperty(navigator, 'share');
  }
}

function recipientsState(over: Partial<PeerRecipientsState> = {}): PeerRecipientsState {
  return {
    recipients: CONNECTIONS as ConnectionView[],
    loading: false,
    error: null,
    ...over,
  };
}

function renderActions(
  over: {
    onPrefillComposer?: (text: string) => void;
    composer?: boolean;
    peersAvailable?: boolean;
    timestamp?: Date;
  } = {}
) {
  const onPrefillComposer =
    over.composer === false ? undefined : (over.onPrefillComposer ?? vi.fn());
  return renderWithProviders(
    <PeersAvailabilityProvider available={over.peersAvailable ?? true}>
      <ShareResponseActions
        content={CONTENT}
        timestamp={over.timestamp ?? TIMESTAMP}
        onPrefillComposer={onPrefillComposer}
      />
    </PeersAvailabilityProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  usePeerRecipientsState.mockReturnValue(recipientsState());
});

afterEach(() => {
  stubNavigatorShare(undefined);
});

describe('Download — one click, everywhere', () => {
  it('exports the raw markdown under a dated lia-prefixed name', async () => {
    const { user } = renderActions();

    await user.click(screen.getByRole('button', { name: 'chat.message.download_md' }));

    expect(downloadMarkdown).toHaveBeenCalledWith(CONTENT, 'lia-2026-07-28-19-42');
  });

  it('zero-pads every date component', async () => {
    // 3 Feb, 08:05 — every component below ten.
    const { user } = renderActions({ timestamp: new Date(2026, 1, 3, 8, 5) });

    await user.click(screen.getByRole('button', { name: 'chat.message.download_md' }));

    expect(downloadMarkdown).toHaveBeenCalledWith(CONTENT, 'lia-2026-02-03-08-05');
  });

  it('is there even where nothing can be shared', () => {
    renderActions({ composer: false });

    expect(screen.getByRole('button', { name: 'chat.message.download_md' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'chat.message.share' })).toBeNull();
  });
});

describe('Share — the platform sheet alone is one click', () => {
  it('hands the raw markdown to the platform share sheet, no menu', async () => {
    const share = vi.fn(async () => {});
    stubNavigatorShare(share);
    const { user } = renderActions({ composer: false });

    await user.click(screen.getByRole('button', { name: 'chat.message.share' }));

    expect(share).toHaveBeenCalledWith({ title: 'LIA', text: CONTENT });
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('treats a dismissed share sheet as a non-event', async () => {
    stubNavigatorShare(
      vi.fn(async () => {
        throw new DOMException('user cancelled', 'AbortError');
      })
    );
    const { user } = renderActions({ composer: false });

    await user.click(screen.getByRole('button', { name: 'chat.message.share' }));

    await waitFor(() => expect(toast.error).not.toHaveBeenCalled());
  });

  it('surfaces a share that actually failed', async () => {
    stubNavigatorShare(
      vi.fn(async () => {
        throw new Error('share broke');
      })
    );
    const { user } = renderActions({ composer: false });

    await user.click(screen.getByRole('button', { name: 'chat.message.share' }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('chat.message.share_error'));
  });

  it('is the direct share when the instance offers no connection', async () => {
    const share = vi.fn(async () => {});
    stubNavigatorShare(share);
    const { user } = renderActions({ peersAvailable: false });

    await user.click(screen.getByRole('button', { name: 'chat.message.share' }));

    expect(share).toHaveBeenCalled();
    expect(usePeerRecipientsState).not.toHaveBeenCalledWith(true);
  });
});

describe('Share — a connection can receive the answer', () => {
  it('reads the connections only once the menu is open', async () => {
    const { user } = renderActions();
    expect(usePeerRecipientsState).not.toHaveBeenCalledWith(true);

    await user.click(screen.getByRole('button', { name: 'chat.message.share' }));

    expect(usePeerRecipientsState).toHaveBeenLastCalledWith(true);
  });

  it('offers the platform sheet beside the connections when the platform has one', async () => {
    const share = vi.fn(async () => {});
    stubNavigatorShare(share);
    const { user } = renderActions();

    await user.click(screen.getByRole('button', { name: 'chat.message.share' }));
    await user.click(await screen.findByRole('menuitem', { name: 'chat.message.share_system' }));

    expect(share).toHaveBeenCalledWith({ title: 'LIA', text: CONTENT });
  });

  it('offers no platform entry where the platform has none', async () => {
    const { user } = renderActions();

    await user.click(screen.getByRole('button', { name: 'chat.message.share' }));

    expect(await screen.findByText('chat.message.share_peer')).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: 'chat.message.share_system' })).toBeNull();
  });

  it('prefills the composer with the recipient and the content, and sends nothing', async () => {
    const onPrefillComposer = vi.fn();
    const { user } = renderActions({ onPrefillComposer });

    await user.click(screen.getByRole('button', { name: 'chat.message.share' }));
    // By ROLE: the recipients are menu items, and picking one is what a
    // keyboard user does too.
    await user.click(await screen.findByRole('menuitem', { name: 'Gérard Dupont' }));

    // Prefilled, never posted: nothing here calls the peer API.
    expect(onPrefillComposer).toHaveBeenCalledTimes(1);
    expect(onPrefillComposer).toHaveBeenCalledWith('chat.message.share_peer_draft');
  });

  it('says the connections are loading', async () => {
    usePeerRecipientsState.mockReturnValue(recipientsState({ recipients: [], loading: true }));
    const { user } = renderActions();

    await user.click(screen.getByRole('button', { name: 'chat.message.share' }));

    expect(await screen.findByText('settings.peers.recipients.loading')).toBeInTheDocument();
  });

  it('says the connections could not be read — never « none »', async () => {
    usePeerRecipientsState.mockReturnValue(
      recipientsState({ recipients: [], error: new Error('503') })
    );
    const { user } = renderActions();

    await user.click(screen.getByRole('button', { name: 'chat.message.share' }));

    expect(await screen.findByText('settings.peers.recipients.load_error')).toBeInTheDocument();
    expect(screen.queryByText('settings.peers.recipients.no_connection')).toBeNull();
  });

  it('says there is no connection yet, and where to make one', async () => {
    usePeerRecipientsState.mockReturnValue(recipientsState({ recipients: [] }));
    const { user } = renderActions();

    await user.click(screen.getByRole('button', { name: 'chat.message.share' }));

    expect(await screen.findByText('settings.peers.recipients.no_connection')).toBeInTheDocument();
  });

  it('builds that draft from the recipient AND the answer', () => {
    // The harness translator is `(key) => key` (src/__tests__/setup.ts), so
    // the interpolated sentence cannot be observed through the DOM. What IS
    // observable — and what a refactor could silently drop — is that the
    // wording declares both placeholders in every locale it ships in.
    for (const lng of ['en', 'fr', 'de', 'es', 'it', 'zh']) {
      const raw = readFileSync(join(process.cwd(), 'locales', lng, 'translation.json'), 'utf-8');
      const wording = (JSON.parse(raw) as { chat: { message: Record<string, string> } }).chat
        .message.share_peer_draft;
      expect(wording, `${lng} must name the recipient`).toContain('{{recipient}}');
      expect(wording, `${lng} must carry the answer`).toContain('{{content}}');
    }
  });
});
