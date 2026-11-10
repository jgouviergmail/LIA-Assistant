/** One bounded SSE answer. Heartbeats keep proxies alive; only an explicit result is success. */
import { z } from '@/lib/zod';
import apiClient, { ApiError } from '@/lib/api-client';
import { logger } from '@/lib/logger';
import { selectionAnswerSchema, type SelectionAnswer, type SelectionOffer } from './contracts';

const MAX_BUFFER_CHARS = 1024 * 1024;
const envelope = z.union([
  z.object({ result: selectionAnswerSchema }).strict(),
  z
    .object({
      error: z.object({ status: z.number().int().min(400).max(599), detail: z.unknown() }),
    })
    .strict(),
]);
function decodeFrame(frame: string): SelectionAnswer | null {
  const data = frame
    .split('\n')
    .filter(line => line.startsWith('data:'))
    .map(line => line.slice(5).trimStart());
  if (!data.length) return null;
  const value = envelope.parse(JSON.parse(data.join('\n')));
  if ('error' in value)
    throw new ApiError('Selection assistance refused', value.error.status, {
      detail: value.error.detail,
    });
  return value.result;
}
export async function readSelectionAnswer(response: Response): Promise<SelectionAnswer> {
  if (!response.body || !response.headers.get('content-type')?.startsWith('text/event-stream'))
    throw new TypeError('Expected an assistance stream');
  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8', { fatal: true });
  let buffer = '';
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) throw new TypeError('Assistance ended without a result');
      buffer += decoder.decode(value, { stream: true });
      if (buffer.length > MAX_BUFFER_CHARS)
        throw new TypeError('Assistance frame exceeds its bound');
      buffer = buffer.replaceAll('\r\n', '\n');
      let boundary: number;
      while ((boundary = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const answer = decodeFrame(frame);
        if (answer) return answer;
      }
    }
  } finally {
    try {
      await reader.cancel();
    } catch {
      logger.debug('selection_stream_cleanup_failed');
    } finally {
      reader.releaseLock();
    }
  }
}
export async function requestSelection(
  path: string,
  body: object,
  signal: AbortSignal,
  offer: SelectionOffer
): Promise<SelectionAnswer> {
  const deadline =
    'action' in body && body.action === 'internet'
      ? offer.internet_timeout_seconds
      : offer.call_timeout_seconds;
  const response = await apiClient.postResponse(path, body, {
    signal,
    timeout: (deadline + 2 * offer.heartbeat_seconds) * 1000,
  });
  return readSelectionAnswer(response);
}
