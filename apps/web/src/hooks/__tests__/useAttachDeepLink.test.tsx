/**
 * `?attach=` — a page's « Use in the discussion » link reaches the composer once.
 *
 * The param leaves the address on arrival (a reload attaches nothing), the copy
 * is the API's, the created row joins the strip, and a refusal is said.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

import { ApiError } from '@/lib/api-client';

const ID = '11111111-2222-4333-8444-555555555555';
const mocks = vi.hoisted(() => ({
  search: new URLSearchParams(),
  post: vi.fn(),
  toast: { error: vi.fn() },
}));
vi.mock('next/navigation', () => ({ useSearchParams: () => mocks.search }));
vi.mock('sonner', () => ({ toast: mocks.toast }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { post: mocks.post },
}));

import { useAttachDeepLink } from '../useAttachDeepLink';

const created = {
  id: 'att-1',
  original_filename: 'Kept answer 2026-10-20.md',
  mime_type: 'text/markdown',
  file_size: 120,
  content_type: 'document' as const,
};

function arrive(value: string) {
  mocks.search = new URLSearchParams({ attach: value });
  window.history.replaceState(null, '', `/en/dashboard/chat?attach=${encodeURIComponent(value)}`);
}

beforeEach(() => {
  mocks.post.mockReset();
  mocks.toast.error.mockReset();
});
afterEach(() => window.history.replaceState(null, '', '/'));

describe('useAttachDeepLink', () => {
  it('copies the named kept answer once and leaves the address at once', async () => {
    arrive(`bookmark:${ID}`);
    mocks.post.mockResolvedValue(created);
    const onAttached = vi.fn(() => ({ ok: true as const }));

    const { rerender } = renderHook(() => useAttachDeepLink(true, onAttached));
    rerender();

    expect(window.location.search).toBe('');
    await waitFor(() => expect(onAttached).toHaveBeenCalledTimes(1));
    expect(mocks.post).toHaveBeenCalledWith('/attachments/from-bookmark', { bookmark_id: ID });
    expect(onAttached).toHaveBeenCalledWith({
      id: 'att-1',
      filename: 'Kept answer 2026-10-20.md',
      mimeType: 'text/markdown',
      size: 120,
      contentType: 'document',
    });
  });

  it('says a file that is gone instead of dropping it in silence', async () => {
    arrive(`generated:${ID}`);
    mocks.post.mockRejectedValue(new ApiError('Not Found', 404));
    const onAttached = vi.fn(() => ({ ok: true as const }));

    renderHook(() => useAttachDeepLink(true, onAttached));

    await waitFor(() => expect(mocks.toast.error).toHaveBeenCalledWith('chat.attach_link.gone'));
    expect(mocks.post).toHaveBeenCalledWith('/attachments/from-generated', { attachment_id: ID });
    expect(onAttached).not.toHaveBeenCalled();
  });

  it('asks nothing of the API for a value that names nothing, or with attachments off', () => {
    arrive('upload:not-an-id');
    renderHook(() => useAttachDeepLink(true, vi.fn()));
    arrive(`bookmark:${ID}`);
    renderHook(() => useAttachDeepLink(false, vi.fn()));

    expect(mocks.post).not.toHaveBeenCalled();
    expect(window.location.search).toBe('');
  });
});
