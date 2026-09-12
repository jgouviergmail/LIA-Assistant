/**
 * The bookmark toggle of an assistant bubble (ADR-282), with the state it
 * reads from the surrounding chat.
 *
 * What it must hold:
 * - nothing is drawn outside a provider, or when the instance does not offer
 *   bookmarks — a control that leads nowhere is worse than none;
 * - the state is read ONCE per chat, and a bubble draws it filled or empty;
 * - a click is optimistic and confirmed by the server; a refusal rolls the icon
 *   back and shows the server's own sentence (the cap, the switch);
 * - the second click removes; a click while the first is in flight is ignored;
 * - the control has a stable translated name in both languages the guard reads.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { BookmarkStateProvider } from '@/lib/bookmark-state-context';

const { api, FakeApiError } = vi.hoisted(() => {
  /** The shape `api-client` throws: a status the component reads, a body the detail comes from. */
  class FakeApiError extends Error {
    constructor(
      public status: number,
      public data: unknown
    ) {
      super(`HTTP ${status}`);
    }
  }
  return { api: { get: vi.fn(), post: vi.fn(), delete: vi.fn() }, FakeApiError };
});
vi.mock('@/lib/api-client', () => ({ default: api, ApiError: FakeApiError }));

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock('sonner', () => ({ toast }));

import { BookmarkButton } from '../BookmarkButton';

const MESSAGE = 'a1b2c3d4-0000-4000-8000-000000000001';
const KEPT = 'b1b2c3d4-0000-4000-8000-000000000009';

function mount(enabled = true) {
  return renderWithProviders(
    <BookmarkStateProvider enabled={enabled}>
      <BookmarkButton messageDbId={MESSAGE} />
    </BookmarkStateProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.get.mockResolvedValue({ message_ids: {} });
  api.post.mockResolvedValue({ id: KEPT, message_id: MESSAGE });
  api.delete.mockResolvedValue(undefined);
});

describe('when it is drawn', () => {
  it('renders nothing outside a provider', () => {
    renderWithProviders(<BookmarkButton messageDbId={MESSAGE} />);

    expect(screen.queryByTestId('bookmark-toggle')).not.toBeInTheDocument();
  });

  it('renders nothing when the instance does not offer bookmarks', () => {
    mount(false);

    expect(screen.queryByTestId('bookmark-toggle')).not.toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalled();
  });

  it('reads the state ONCE for the chat and draws a kept answer filled', async () => {
    api.get.mockResolvedValue({ message_ids: { [MESSAGE]: KEPT } });

    mount();

    await waitFor(() =>
      expect(screen.getByTestId('bookmark-toggle')).toHaveAttribute('aria-pressed', 'true')
    );
    expect(api.get).toHaveBeenCalledTimes(1);
    expect(api.get).toHaveBeenCalledWith('/bookmarks/state');
  });
});

describe('the toggle', () => {
  it('keeps on the first click and says so', async () => {
    const { user } = mount();
    const button = await screen.findByTestId('bookmark-toggle');
    expect(button).toHaveAttribute('aria-pressed', 'false');

    await user.click(button);

    await waitFor(() => expect(button).toHaveAttribute('aria-pressed', 'true'));
    expect(api.post).toHaveBeenCalledWith('/bookmarks', { message_id: MESSAGE });
    expect(toast.success).toHaveBeenCalledWith('chat.message.bookmark_kept');
  });

  it('removes on the second click', async () => {
    api.get.mockResolvedValue({ message_ids: { [MESSAGE]: KEPT } });
    const { user } = mount();
    const button = await screen.findByTestId('bookmark-toggle');
    await waitFor(() => expect(button).toHaveAttribute('aria-pressed', 'true'));

    await user.click(button);

    await waitFor(() => expect(button).toHaveAttribute('aria-pressed', 'false'));
    expect(api.delete).toHaveBeenCalledWith(`/bookmarks/by-message/${MESSAGE}`);
    expect(toast.success).toHaveBeenCalledWith('chat.message.bookmark_removed');
  });

  it('rolls the icon back and shows the server sentence when keeping is refused', async () => {
    // The cap (409) and the operator switch (403) both come back as a
    // translated `detail`: that sentence is what the person reads.
    api.post.mockRejectedValue(
      new FakeApiError(409, { detail: 'Vous avez atteint la limite de 500 bookmarks.' })
    );
    const { user } = mount();
    const button = await screen.findByTestId('bookmark-toggle');

    await user.click(button);

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('Vous avez atteint la limite de 500 bookmarks.')
    );
    expect(button).toHaveAttribute('aria-pressed', 'false');
  });

  it('falls back to its own sentence when the refusal carries none', async () => {
    api.post.mockRejectedValue(new Error('network'));
    const { user } = mount();

    await user.click(await screen.findByTestId('bookmark-toggle'));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('chat.message.bookmark_error'));
  });

  it('never shows an untranslated 404 detail', async () => {
    // A message the server does not know answers 404 with an English
    // fallback sentence; the person reads this component's own words.
    api.post.mockRejectedValue(new FakeApiError(404, { detail: 'Bookmark not found' }));
    const { user } = mount();

    await user.click(await screen.findByTestId('bookmark-toggle'));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('chat.message.bookmark_error'));
  });

  it('keeps a click confirmed while the state read was still in flight', async () => {
    // The read returns the OLDER map; merged under the person's own click,
    // it must not empty an icon the server has already filled.
    let settleState: (value: { message_ids: Record<string, string> }) => void = () => undefined;
    api.get.mockReturnValue(new Promise(resolve => (settleState = resolve)));
    const { user } = mount();
    const button = await screen.findByTestId('bookmark-toggle');

    await user.click(button);
    await waitFor(() => expect(button).toHaveAttribute('aria-pressed', 'true'));
    settleState({ message_ids: {} });

    await waitFor(() => expect(api.get).toHaveBeenCalled());
    await new Promise(resolve => setTimeout(resolve, 0));
    expect(button).toHaveAttribute('aria-pressed', 'true');
  });

  it('ignores a second click while the first is still in flight', async () => {
    let settle: (value: { id: string }) => void = () => undefined;
    api.post.mockReturnValue(new Promise(resolve => (settle = resolve)));
    const { user } = mount();
    const button = await screen.findByTestId('bookmark-toggle');

    await user.click(button);
    await user.click(button);
    settle({ id: KEPT });

    await waitFor(() => expect(button).toHaveAttribute('aria-pressed', 'true'));
    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.delete).not.toHaveBeenCalled();
  });
});

describe('its accessible name', () => {
  it.each(['en', 'fr'])('is a real sentence in %s, for both states', lng => {
    const path = join(__dirname, '..', '..', '..', '..', 'locales', lng, 'translation.json');
    const messages = JSON.parse(readFileSync(path, 'utf-8')).chat.message;

    for (const key of ['bookmark', 'bookmark_remove', 'bookmark_kept', 'bookmark_removed']) {
      expect(messages[key]).toEqual(expect.any(String));
      expect(messages[key].length).toBeGreaterThan(8);
    }
  });

  it('names the current state, not the icon', async () => {
    mount();
    const button = await screen.findByTestId('bookmark-toggle');

    expect(button).toHaveAccessibleName('chat.message.bookmark');
  });
});
