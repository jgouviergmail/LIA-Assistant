/**
 * useFileUpload — the attachment pipeline behind the composer: client-side
 * validation, XHR upload with progress, and the resource discipline that keeps
 * it from leaking (every in-flight request aborted and every preview Object URL
 * revoked on removal, on clear and on unmount).
 *
 * The XHR is replaced by a controllable fake so every branch — 201, non-201,
 * unparsable body, network error, timeout, abort — is driven explicitly rather
 * than hoped for. `isImageFile` stays real (it is the pure predicate the
 * validation hangs on); only `compressImage`, which needs a canvas, is stubbed.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderHook, act, waitFor } from '@/__tests__/test-utils';

const { compressImage } = vi.hoisted(() => ({ compressImage: vi.fn() }));
vi.mock('@/lib/utils/image-compress', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/utils/image-compress')>();
  return { ...actual, compressImage };
});

import { useFileUpload } from '../useFileUpload';

type UploadHook = ReturnType<typeof useFileUpload>;
type UploadOutcome = Awaited<ReturnType<UploadHook['uploadFile']>>;

interface ProgressEvent {
  lengthComputable: boolean;
  loaded: number;
  total: number;
}

/** A controllable XMLHttpRequest: the test decides how each upload ends. */
class FakeXhr {
  static instances: FakeXhr[] = [];

  upload: { onprogress: ((e: ProgressEvent) => void) | null } = { onprogress: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  ontimeout: (() => void) | null = null;
  status = 201;
  responseText = JSON.stringify({ id: 'att-1' });
  timeout = 0;
  withCredentials = false;
  method = '';
  url = '';
  body: unknown = null;
  aborted = false;

  constructor() {
    FakeXhr.instances.push(this);
  }

  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }

  send(body: unknown) {
    this.body = body;
  }

  abort() {
    this.aborted = true;
  }
}

const png = (name = 'photo.png', size = 1_000) => {
  const file = new File(['x'], name, { type: 'image/png' });
  Object.defineProperty(file, 'size', { value: size });
  return file;
};

const pdf = (size = 1_000) => {
  const file = new File(['x'], 'doc.pdf', { type: 'application/pdf' });
  Object.defineProperty(file, 'size', { value: size });
  return file;
};

const MB = 1024 * 1024;

const createObjectURL = vi.fn(() => 'blob:preview');
const revokeObjectURL = vi.fn();

/** Waits for the hook to have created the XHR (it awaits compression first). */
async function pendingXhr(index = 0): Promise<FakeXhr> {
  await waitFor(() => expect(FakeXhr.instances.length).toBeGreaterThan(index));
  return FakeXhr.instances[index];
}

beforeEach(() => {
  vi.clearAllMocks();
  FakeXhr.instances = [];
  compressImage.mockImplementation(async (file: File) => ({ blob: file, width: 0, height: 0 }));
  vi.stubGlobal('XMLHttpRequest', FakeXhr);
  Object.defineProperty(URL, 'createObjectURL', { value: createObjectURL, configurable: true });
  Object.defineProperty(URL, 'revokeObjectURL', { value: revokeObjectURL, configurable: true });
});

afterEach(() => vi.unstubAllGlobals());

describe('useFileUpload — validation', () => {
  it('refuses a document type that is not on the allow-list', async () => {
    const { result } = renderHook(() => useFileUpload());
    const file = new File(['x'], 'setup.exe', { type: 'application/x-msdownload' });

    let outcome!: UploadOutcome;
    await act(async () => {
      outcome = await result.current.uploadFile(file);
    });

    expect(outcome).toEqual({ error: 'type_not_allowed' });
    expect(result.current.attachments).toHaveLength(0);
    expect(FakeXhr.instances).toHaveLength(0);
  });

  it('lets an unknown image subtype through (the HEIC quirk)', async () => {
    const { result } = renderHook(() => useFileUpload());
    const heic = new File(['x'], 'IMG.heic', { type: 'image/x-unknown-subtype' });

    act(() => {
      void result.current.uploadFile(heic);
    });

    await pendingXhr();
    expect(result.current.attachments[0]).toMatchObject({ contentType: 'image' });
  });

  it('refuses an image above the image limit', async () => {
    const { result } = renderHook(() => useFileUpload({ maxImageSizeMB: 1 }));

    let outcome!: UploadOutcome;
    await act(async () => {
      outcome = await result.current.uploadFile(png('big.png', 2 * MB));
    });

    expect(outcome).toEqual({ error: 'file_too_large' });
  });

  it('applies the document limit to documents, not the image one', async () => {
    // 15 MB doc: over the 10 MB image limit, under the 20 MB document limit.
    const { result } = renderHook(() => useFileUpload());

    act(() => {
      void result.current.uploadFile(pdf(15 * MB));
    });

    await pendingXhr();
    expect(result.current.attachments[0]).toMatchObject({ contentType: 'document' });
  });

  it('caps the number of attachments even when uploads start together', async () => {
    const { result } = renderHook(() => useFileUpload({ maxAttachments: 3 }));

    // Fired in the same tick: the guard cannot rely on rendered state.
    const outcomes: Promise<UploadOutcome>[] = [];
    act(() => {
      for (let i = 0; i < 5; i++) outcomes.push(result.current.uploadFile(png(`p${i}.png`)));
    });

    const settled = await Promise.all(outcomes.slice(3));
    expect(settled).toEqual([{ error: 'max_attachments' }, { error: 'max_attachments' }]);
    await waitFor(() => expect(result.current.attachments).toHaveLength(3));
  });
});

describe('useFileUpload — upload lifecycle', () => {
  it('sends the file with credentials to the attachments endpoint', async () => {
    const { result } = renderHook(() => useFileUpload());

    act(() => {
      void result.current.uploadFile(png());
    });
    const xhr = await pendingXhr();

    expect(xhr.method).toBe('POST');
    expect(xhr.url).toMatch(/\/attachments\/upload$/);
    expect(xhr.withCredentials).toBe(true);
    expect(xhr.timeout).toBeGreaterThan(0);
    expect(xhr.body).toBeInstanceOf(FormData);
  });

  it('previews an image immediately and marks it uploading', async () => {
    const { result } = renderHook(() => useFileUpload());

    act(() => {
      void result.current.uploadFile(png());
    });

    await waitFor(() => expect(result.current.attachments).toHaveLength(1));
    expect(result.current.attachments[0]).toMatchObject({
      filename: 'photo.png',
      status: 'uploading',
      progress: 0,
      previewUrl: 'blob:preview',
    });
    expect(result.current.isUploading).toBe(true);
  });

  it('builds no preview for a document', async () => {
    const { result } = renderHook(() => useFileUpload());

    act(() => {
      void result.current.uploadFile(pdf());
    });

    await waitFor(() => expect(result.current.attachments).toHaveLength(1));
    expect(result.current.attachments[0].previewUrl).toBeUndefined();
    expect(createObjectURL).not.toHaveBeenCalled();
  });

  it('reports the upload progress', async () => {
    const { result } = renderHook(() => useFileUpload());
    act(() => {
      void result.current.uploadFile(png());
    });
    const xhr = await pendingXhr();

    act(() => xhr.upload.onprogress?.({ lengthComputable: true, loaded: 30, total: 120 }));
    expect(result.current.attachments[0].progress).toBe(25);

    // A non-measurable stream must not reset what was already shown.
    act(() => xhr.upload.onprogress?.({ lengthComputable: false, loaded: 0, total: 0 }));
    expect(result.current.attachments[0].progress).toBe(25);
  });

  it('marks the attachment ready with the id the server assigned', async () => {
    const { result } = renderHook(() => useFileUpload());
    let outcome!: UploadOutcome;
    act(() => {
      void result.current.uploadFile(png()).then(o => {
        outcome = o;
      });
    });
    const xhr = await pendingXhr();

    await act(async () => {
      xhr.onload?.();
    });

    expect(outcome).toEqual({ success: true });
    expect(result.current.attachments[0]).toMatchObject({
      status: 'ready',
      progress: 100,
      attachmentId: 'att-1',
    });
    expect(result.current.isUploading).toBe(false);
    expect(result.current.getReadyAttachmentIds()).toEqual(['att-1']);
  });

  it('records the compressed size rather than the original one', async () => {
    compressImage.mockResolvedValue({ blob: new Blob(['tiny']), width: 10, height: 10 });
    const { result } = renderHook(() => useFileUpload());

    act(() => {
      void result.current.uploadFile(png('photo.png', 5_000));
    });

    await waitFor(() => expect(result.current.attachments[0]?.size).toBe(4));
  });
});

describe('useFileUpload — failures', () => {
  /** Runs an upload to the point where the test can end it however it likes. */
  async function startUpload() {
    const { result } = renderHook(() => useFileUpload());
    let outcome: UploadOutcome | undefined;
    act(() => {
      void result.current.uploadFile(png()).then(o => {
        outcome = o;
      });
    });
    const xhr = await pendingXhr();
    return { result, xhr, read: () => outcome };
  }

  it('fails on a rejected status and keeps the reason on the attachment', async () => {
    const { result, xhr, read } = await startUpload();

    await act(async () => {
      xhr.status = 413;
      xhr.onload?.();
    });

    expect(read()).toEqual({ error: 'upload_failed' });
    expect(result.current.attachments[0]).toMatchObject({
      status: 'error',
      error: 'Upload failed: 413',
    });
  });

  it('fails on a 201 whose body cannot be read', async () => {
    const { result, xhr, read } = await startUpload();

    await act(async () => {
      xhr.responseText = 'not json';
      xhr.onload?.();
    });

    expect(read()).toEqual({ error: 'upload_failed' });
    expect(result.current.attachments[0]).toMatchObject({ error: 'Invalid response' });
  });

  it('fails on a network error', async () => {
    const { result, xhr, read } = await startUpload();

    await act(async () => {
      xhr.onerror?.();
    });

    expect(read()).toEqual({ error: 'upload_failed' });
    expect(result.current.attachments[0]).toMatchObject({ error: 'Network error' });
  });

  it('fails when the upload times out', async () => {
    const { result, xhr, read } = await startUpload();

    await act(async () => {
      xhr.ontimeout?.();
    });

    expect(read()).toEqual({ error: 'upload_failed' });
    expect(result.current.attachments[0]).toMatchObject({ error: 'Upload timeout' });
  });

  it('reports a compression failure as an upload failure', async () => {
    compressImage.mockRejectedValue(new Error('canvas unavailable'));
    const { result } = renderHook(() => useFileUpload());

    let outcome!: UploadOutcome;
    await act(async () => {
      outcome = await result.current.uploadFile(png());
    });

    expect(outcome).toEqual({ error: 'upload_failed' });
    expect(FakeXhr.instances).toHaveLength(0);
    expect(result.current.attachments[0]).toMatchObject({ status: 'error' });
  });

  it('leaves a failed attachment out of what gets sent', async () => {
    const { result, xhr } = await startUpload();
    await act(async () => {
      xhr.onerror?.();
    });

    expect(result.current.getReadyAttachmentIds()).toEqual([]);
  });
});

describe('useFileUpload — cancellation and cleanup', () => {
  it('aborts the request and revokes the preview when a file is removed', async () => {
    const { result } = renderHook(() => useFileUpload());
    act(() => {
      void result.current.uploadFile(png());
    });
    const xhr = await pendingXhr();
    const { tempId } = result.current.attachments[0];

    act(() => result.current.removeFile(tempId));

    expect(xhr.aborted).toBe(true);
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:preview');
    expect(result.current.attachments).toHaveLength(0);
  });

  it('ignores a removal for an unknown attachment', async () => {
    const { result } = renderHook(() => useFileUpload());
    act(() => {
      void result.current.uploadFile(png());
    });
    await pendingXhr();

    act(() => result.current.removeFile('does-not-exist'));

    expect(result.current.attachments).toHaveLength(1);
    expect(revokeObjectURL).not.toHaveBeenCalled();
  });

  it('aborts everything and revokes every preview when the draft is cleared', async () => {
    const { result } = renderHook(() => useFileUpload());
    act(() => {
      void result.current.uploadFile(png('a.png'));
      void result.current.uploadFile(png('b.png'));
    });
    await pendingXhr(1);

    act(() => result.current.clearAttachments());

    expect(FakeXhr.instances.every(x => x.aborted)).toBe(true);
    expect(revokeObjectURL).toHaveBeenCalledTimes(2);
    expect(result.current.attachments).toHaveLength(0);
  });

  it('does not leak a request or an Object URL when the composer unmounts', async () => {
    const { result, unmount } = renderHook(() => useFileUpload());
    act(() => {
      void result.current.uploadFile(png());
    });
    const xhr = await pendingXhr();

    unmount();

    expect(xhr.aborted).toBe(true);
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:preview');
  });
});
