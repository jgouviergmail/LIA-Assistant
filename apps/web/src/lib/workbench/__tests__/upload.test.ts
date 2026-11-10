/**
 * One file sent, its progress read (ADR-369, lot 6).
 *
 * The session cookie travels, the API's own origin is reached, a refusal keeps the
 * API's words for `workbenchRefusal`, and stopping aborts what is on its way.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api-client';

import { FileSendStopped, sendFile } from '../upload';

class FakeRequest {
  static last: FakeRequest;
  upload: { onprogress: ((event: Partial<ProgressEvent>) => void) | null } = { onprogress: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  ontimeout: (() => void) | null = null;
  onabort: (() => void) | null = null;
  status = 0;
  responseText = '';
  withCredentials = false;
  timeout = 0;
  opened: [string, string] | null = null;
  body: unknown = null;
  aborted = false;
  headers = new Headers();

  constructor() {
    FakeRequest.last = this;
  }
  open(method: string, url: string) {
    this.opened = [method, url];
  }
  setRequestHeader(name: string, value: string) {
    this.headers.set(name, value);
  }
  send(body: unknown) {
    this.body = body;
  }
  abort() {
    this.aborted = true;
    this.onabort?.();
  }
  answer(status: number, body: unknown) {
    this.status = status;
    this.responseText = typeof body === 'string' ? body : JSON.stringify(body);
    this.onload?.();
  }
}

const form = new FormData();
const originalUrl = window.location.href;

function sent(onProgress = vi.fn(), signal = new AbortController().signal) {
  return sendFile<{ id: string }>('/workbench/files/upload', form, onProgress, signal);
}

beforeEach(() => {
  vi.stubGlobal('XMLHttpRequest', FakeRequest);
});

afterEach(() => {
  window.history.replaceState(null, '', originalUrl);
  vi.unstubAllGlobals();
});

describe('sendFile', () => {
  it('guards an upload against a source replaced after the card opened', async () => {
    window.history.replaceState(null, '', '/dashboard/tools/files?card_source=upload-proof');
    const answer = sent();
    expect(FakeRequest.last.headers.get('X-LIA-Card-Source')).toBe('upload-proof');
    expect(
      new URL(FakeRequest.last.opened![1], window.location.origin).searchParams.get('card_source')
    ).toBe('upload-proof');
    FakeRequest.last.answer(409, { detail: { code: 'card_source_changed' } });
    await expect(answer).rejects.toMatchObject({
      status: 409,
      data: { detail: { code: 'card_source_changed' } },
    });
  });
  it('posts the form to the API with the session cookie, under a bound', () => {
    void sent();

    expect(FakeRequest.last.opened?.[0]).toBe('POST');
    expect(FakeRequest.last.opened?.[1]).toContain('/workbench/files/upload');
    expect(FakeRequest.last.withCredentials).toBe(true);
    expect(FakeRequest.last.timeout).toBeGreaterThan(0);
    expect(FakeRequest.last.body).toBe(form);
  });

  it('answers what the API answered', async () => {
    const answered = sent();

    FakeRequest.last.answer(201, { id: 'f1' });

    await expect(answered).resolves.toEqual({ id: 'f1' });
  });

  it('keeps the API’s own refusal, for the screen to say', async () => {
    const answered = sent();

    FakeRequest.last.answer(409, { detail: { code: 'name_taken' } });

    const error = await answered.catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(409);
    expect((error as ApiError).data).toEqual({ detail: { code: 'name_taken' } });
  });

  it('survives an answer that is not JSON: a proxy’s page is still a refusal', async () => {
    const answered = sent();

    FakeRequest.last.answer(502, '<html>bad gateway</html>');

    const error = await answered.catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(502);
  });

  it('reads its progress, in percent', () => {
    const onProgress = vi.fn();
    void sent(onProgress);

    FakeRequest.last.upload.onprogress?.({ lengthComputable: true, loaded: 25, total: 100 });
    FakeRequest.last.upload.onprogress?.({ lengthComputable: false, loaded: 50, total: 0 });

    expect(onProgress.mock.calls).toEqual([[25]]);
  });

  it('rejects a connection lost, and a bound passed', async () => {
    const lost = sent();
    FakeRequest.last.onerror?.();
    await expect(lost).rejects.toBeInstanceOf(Error);

    const late = sent();
    FakeRequest.last.ontimeout?.();
    await expect(late).rejects.toBeInstanceOf(Error);
  });

  it('stops what is on its way when asked', async () => {
    const stop = new AbortController();
    const answered = sent(vi.fn(), stop.signal);

    stop.abort();

    await expect(answered).rejects.toBeInstanceOf(FileSendStopped);
    expect(FakeRequest.last.aborted).toBe(true);
  });

  it('sends nothing when already stopped', async () => {
    const stop = new AbortController();
    stop.abort();

    await expect(sent(vi.fn(), stop.signal)).rejects.toBeInstanceOf(FileSendStopped);
  });
});
