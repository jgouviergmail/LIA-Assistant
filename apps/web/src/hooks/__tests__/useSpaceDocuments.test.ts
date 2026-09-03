/**
 * useSpaceDocuments — uploading and removing the documents a RAG space is built
 * from. Same XHR discipline as the chat attachments, with two specifics:
 *
 *  - the server's own `detail` is preferred over a generic HTTP message, so a
 *    refused document tells the user *why* (unsupported type, quota…);
 *  - while a document is being indexed the hook polls the caller's refresh
 *    callback, and that interval must die with the last processing document —
 *    a poll that outlives it hammers the API for nothing.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderHook, act, waitFor } from '@/__tests__/test-utils';
import { mutateSpy, mutationResult } from '@/__tests__/api-mocks';

const { useApiMutation } = vi.hoisted(() => ({ useApiMutation: vi.fn() }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation }));

import { useSpaceDocuments, STATUS_POLL_INTERVAL_MS } from '../useSpaceDocuments';
import type { RAGDocument } from '@/types/rag-spaces';

interface ProgressEvent {
  lengthComputable: boolean;
  loaded: number;
  total: number;
}

/** A controllable XMLHttpRequest, as in the chat-attachment suite. */
class FakeXhr {
  static instances: FakeXhr[] = [];

  upload: { onprogress: ((e: ProgressEvent) => void) | null } = { onprogress: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  ontimeout: (() => void) | null = null;
  onabort: (() => void) | null = null;
  status = 201;
  responseText = JSON.stringify({ id: 'doc-1', filename: 'notes.pdf' });
  timeout = 0;
  withCredentials = false;
  method = '';
  url = '';
  aborted = false;

  constructor() {
    FakeXhr.instances.push(this);
  }

  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }

  send() {}

  abort() {
    this.aborted = true;
    this.onabort?.();
  }
}

const pdf = (name = 'notes.pdf') => new File(['x'], name, { type: 'application/pdf' });

function document(over: Partial<RAGDocument> = {}): RAGDocument {
  return {
    id: 'doc-1',
    original_filename: 'notes.pdf',
    file_size: 1024,
    content_type: 'application/pdf',
    status: 'ready',
    error_message: null,
    chunk_count: 3,
    embedding_model: 'text-embedding-3-small',
    embedding_tokens: 120,
    embedding_cost_eur: 0.0001,
    source_type: 'upload',
    drive_file_id: null,
    created_at: '2026-01-01T00:00:00Z',
    ...over,
  };
}

const remove = mutateSpy();

function setup(documents: RAGDocument[] = [], onDocumentReady = vi.fn()) {
  const hook = renderHook(() =>
    useSpaceDocuments({ spaceId: 'space-1', documents, onDocumentReady })
  );
  return { ...hook, onDocumentReady };
}

/** Waits for the XHR the hook creates, then hands it over. */
async function pendingXhr(index = 0): Promise<FakeXhr> {
  await waitFor(() => expect(FakeXhr.instances.length).toBeGreaterThan(index));
  return FakeXhr.instances[index];
}

beforeEach(() => {
  vi.clearAllMocks();
  FakeXhr.instances = [];
  remove.mockResolvedValue(undefined);
  useApiMutation.mockReturnValue(mutationResult({ mutate: remove }));
  vi.stubGlobal('XMLHttpRequest', FakeXhr);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('useSpaceDocuments — uploading', () => {
  it('posts the document to the space route with credentials', async () => {
    const { result } = setup();

    act(() => {
      void result.current.uploadDocument(pdf());
    });
    const xhr = await pendingXhr();

    expect(xhr.method).toBe('POST');
    expect(xhr.url).toBe('/api/rag-upload/space-1');
    expect(xhr.withCredentials).toBe(true);
    expect(xhr.timeout).toBeGreaterThan(0);
  });

  it('tracks the upload and reports it done, then asks for a refresh', async () => {
    const { result, onDocumentReady } = setup();
    let outcome: { success?: boolean; error?: string } | undefined;

    act(() => {
      void result.current.uploadDocument(pdf()).then(o => {
        outcome = o;
      });
    });
    const xhr = await pendingXhr();

    expect(result.current.uploads[0]).toMatchObject({ filename: 'notes.pdf', status: 'uploading' });
    expect(result.current.isUploading).toBe(true);

    act(() => xhr.upload.onprogress?.({ lengthComputable: true, loaded: 1, total: 4 }));
    expect(result.current.uploads[0].progress).toBe(25);

    await act(async () => {
      xhr.onload?.();
    });

    expect(outcome).toEqual({ success: true });
    expect(result.current.uploads[0]).toMatchObject({ status: 'done', progress: 100 });
    expect(result.current.isUploading).toBe(false);
    // The space now has one more document: the caller must refetch.
    expect(onDocumentReady).toHaveBeenCalled();
  });

  it('accepts a 200 as readily as a 201', async () => {
    const { result } = setup();
    act(() => {
      void result.current.uploadDocument(pdf());
    });
    const xhr = await pendingXhr();

    await act(async () => {
      xhr.status = 200;
      xhr.onload?.();
    });

    expect(result.current.uploads[0].status).toBe('done');
  });
});

describe('useSpaceDocuments — refused uploads', () => {
  async function failWith(mutateXhr: (xhr: FakeXhr) => void) {
    const { result, onDocumentReady } = setup();
    let outcome: { success?: boolean; error?: string } | undefined;
    act(() => {
      void result.current.uploadDocument(pdf()).then(o => {
        outcome = o;
      });
    });
    const xhr = await pendingXhr();
    await act(async () => {
      mutateXhr(xhr);
    });
    return { result, onDocumentReady, read: () => outcome };
  }

  it('prefers the reason the server gave over the status code', async () => {
    const { result, read } = await failWith(xhr => {
      xhr.status = 415;
      xhr.responseText = JSON.stringify({ detail: 'Format non pris en charge' });
      xhr.onload?.();
    });

    expect(read()).toEqual({ error: 'Format non pris en charge' });
    expect(result.current.uploads[0]).toMatchObject({
      status: 'error',
      error: 'Format non pris en charge',
    });
  });

  it('falls back to the status when the error body is unreadable', async () => {
    const { read } = await failWith(xhr => {
      xhr.status = 500;
      xhr.responseText = 'gateway exploded';
      xhr.onload?.();
    });

    expect(read()).toEqual({ error: 'Upload failed: 500' });
  });

  it('reports an unreadable success body', async () => {
    const { read } = await failWith(xhr => {
      xhr.responseText = 'not json';
      xhr.onload?.();
    });

    expect(read()).toEqual({ error: 'Invalid response' });
  });

  it.each([
    ['a network error', (xhr: FakeXhr) => xhr.onerror?.(), 'Network error'],
    ['a timeout', (xhr: FakeXhr) => xhr.ontimeout?.(), 'Upload timeout'],
    ['an abort', (xhr: FakeXhr) => xhr.onabort?.(), 'Upload aborted'],
  ])('reports %s', async (_label, trigger, message) => {
    const { read, onDocumentReady } = await failWith(xhr => trigger(xhr));

    expect(read()).toEqual({ error: message });
    // A failed upload adds nothing to the space: no refresh is warranted.
    expect(onDocumentReady).not.toHaveBeenCalled();
  });
});

describe('useSpaceDocuments — managing the list', () => {
  it('deletes a document from its space and refreshes', async () => {
    const { result, onDocumentReady } = setup([document()]);

    await act(async () => {
      await result.current.deleteDocument('doc-1');
    });

    expect(remove).toHaveBeenCalledWith('/rag-spaces/space-1/documents/doc-1');
    expect(onDocumentReady).toHaveBeenCalled();
  });

  it('aborts the request when an upload entry is dismissed', async () => {
    const { result } = setup();
    act(() => {
      void result.current.uploadDocument(pdf());
    });
    const xhr = await pendingXhr();
    const { tempId } = result.current.uploads[0];

    await act(async () => {
      result.current.dismissUpload(tempId);
    });

    expect(xhr.aborted).toBe(true);
    expect(result.current.uploads).toHaveLength(0);
  });

  it('keeps the uploads still running when the finished ones are cleared', async () => {
    const { result } = setup();
    act(() => {
      void result.current.uploadDocument(pdf('done.pdf'));
    });
    const first = await pendingXhr();
    await act(async () => {
      first.onload?.();
    });
    act(() => {
      void result.current.uploadDocument(pdf('running.pdf'));
    });
    await pendingXhr(1);

    act(() => result.current.clearCompletedUploads());

    expect(result.current.uploads.map(u => u.filename)).toEqual(['running.pdf']);
  });

  it('does not leak a request when the panel closes mid-upload', async () => {
    const { result, unmount } = setup();
    act(() => {
      void result.current.uploadDocument(pdf());
    });
    const xhr = await pendingXhr();

    unmount();

    expect(xhr.aborted).toBe(true);
  });
});

describe('useSpaceDocuments — indexing poll', () => {
  it('asks for a refresh while a document is still processing', () => {
    vi.useFakeTimers();
    const { onDocumentReady } = setup([document({ status: 'processing' })]);

    vi.advanceTimersByTime(STATUS_POLL_INTERVAL_MS);

    expect(onDocumentReady).toHaveBeenCalled();
  });

  it('never polls when everything is already indexed', () => {
    vi.useFakeTimers();
    const { onDocumentReady } = setup([document({ status: 'ready' })]);

    vi.advanceTimersByTime(STATUS_POLL_INTERVAL_MS * 12);

    expect(onDocumentReady).not.toHaveBeenCalled();
  });

  it('stops polling once the last document finishes indexing', () => {
    vi.useFakeTimers();
    const onDocumentReady = vi.fn();
    const { rerender } = renderHook(
      ({ documents }) => useSpaceDocuments({ spaceId: 'space-1', documents, onDocumentReady }),
      { initialProps: { documents: [document({ status: 'processing' })] } }
    );

    vi.advanceTimersByTime(STATUS_POLL_INTERVAL_MS);
    const pollsWhileProcessing = onDocumentReady.mock.calls.length;
    expect(pollsWhileProcessing).toBeGreaterThan(0);

    rerender({ documents: [document({ status: 'ready' })] });
    vi.advanceTimersByTime(STATUS_POLL_INTERVAL_MS * 12);

    expect(onDocumentReady).toHaveBeenCalledTimes(pollsWhileProcessing);
  });
});

describe('useSpaceDocuments — batches and links (ADR-259)', () => {
  it('moves documents to another space and refreshes', async () => {
    const { result, onDocumentReady } = setup([document()]);
    remove.mockResolvedValueOnce({ done: ['doc-1'], skipped: [] });

    let response: unknown;
    await act(async () => {
      response = await result.current.moveDocuments(['doc-1'], 'space-2');
    });

    expect(remove).toHaveBeenCalledWith('/rag-spaces/space-1/documents/move', {
      ids: ['doc-1'],
      target_space_id: 'space-2',
    });
    expect(response).toEqual({ done: ['doc-1'], skipped: [] });
    expect(onDocumentReady).toHaveBeenCalled();
  });

  it('deletes several documents at once and refreshes', async () => {
    const { result, onDocumentReady } = setup([document()]);
    remove.mockResolvedValueOnce({ done: ['doc-1'], skipped: [] });

    await act(async () => {
      await result.current.bulkDeleteDocuments(['doc-1']);
    });

    expect(remove).toHaveBeenCalledWith('/rag-spaces/space-1/documents/bulk-delete', {
      ids: ['doc-1'],
    });
    expect(onDocumentReady).toHaveBeenCalled();
  });

  it('builds the download and archive links on the API origin', () => {
    const { result } = setup();
    expect(result.current.downloadHref('doc-1')).toMatch(
      /\/rag-spaces\/space-1\/documents\/doc-1\/download$/
    );
    expect(result.current.archiveHref(['a', 'b'])).toMatch(
      /\/rag-spaces\/space-1\/documents\/archive\?ids=a,b$/
    );
  });
});
