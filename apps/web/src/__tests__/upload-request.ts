import { vi } from 'vitest';

/** Controlled upload transport: choosing a file alone must never send it. */
export class UploadRequest {
  static sent: UploadRequest[] = [];
  upload = { onprogress: null as ((event: ProgressEvent) => void) | null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  ontimeout: (() => void) | null = null;
  onabort: (() => void) | null = null;
  status = 200;
  responseText = '';
  timeout = 0;
  withCredentials = false;
  open = vi.fn();
  setRequestHeader = vi.fn();
  data: FormData | null = null;
  send = vi.fn((data: FormData) => { this.data = data; UploadRequest.sent.push(this); });
  abort = vi.fn(() => this.onabort?.());
}
