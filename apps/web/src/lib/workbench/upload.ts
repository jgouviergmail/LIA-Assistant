/**
 * One file sent to the API, its progress read (ADR-369, lot 6).
 *
 * Through XHR because `fetch` reads no upload progress, as `useFileUpload` does. The
 * session cookie travels; a refusal keeps the API's own words, for `workbenchRefusal`;
 * stopping aborts what is on its way, and what became of it is the provider's to know.
 */
import { ApiError, apiEndpointUrl } from '@/lib/api-client';

/** Past it the wait is over: the server's own bound on the bytes, and a margin. */
const SEND_TIMEOUT_MS = 180_000;

/** The person stopped the send. */
export class FileSendStopped extends Error {}

function answerOf(request: XMLHttpRequest): unknown {
  try {
    return JSON.parse(request.responseText);
  } catch {
    // A proxy's page is no answer of ours: the status alone is told.
    return undefined;
  }
}

/**
 * Sends a form, and answers what the API answered.
 *
 * @param path - The API path.
 * @param form - The form, its file included.
 * @param onProgress - Told how far the bytes went, in percent.
 * @param signal - Stops the send.
 */
export function sendFile<T>(
  path: string,
  form: FormData,
  onProgress: (percent: number) => void,
  signal: AbortSignal
): Promise<T> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new FileSendStopped());
      return;
    }
    const request = new XMLHttpRequest();
    const stop = () => request.abort();
    const settled = () => signal.removeEventListener('abort', stop);
    request.upload.onprogress = event => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100));
    };
    request.onload = () => {
      settled();
      const answer = answerOf(request);
      if (request.status >= 200 && request.status < 300) resolve(answer as T);
      else reject(new ApiError(`Upload failed: ${request.status}`, request.status, answer));
    };
    request.onerror = () => {
      settled();
      reject(new Error('Network error'));
    };
    request.ontimeout = () => {
      settled();
      reject(new Error('Upload timeout'));
    };
    request.onabort = () => {
      settled();
      reject(new FileSendStopped());
    };
    signal.addEventListener('abort', stop);
    request.open('POST', apiEndpointUrl(path));
    request.withCredentials = true;
    request.timeout = SEND_TIMEOUT_MS;
    request.send(form);
  });
}
