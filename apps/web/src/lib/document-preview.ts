/** Preview reads stay on our API; never forward cookies to a wire URL's host. */
import { attachmentIdFromUrl } from '@/lib/peers/image-share';
import { apiClient } from '@/lib/api-client';

export function documentPreviewUrl(source: string): string | null {
  if (!source.startsWith('/api/v1/attachments/')) return null;
  const id = attachmentIdFromUrl(source);
  return id ? `/api/v1/attachments/${id}/preview` : null;
}

export async function fetchDocumentPreview(wireUrl: string, signal: AbortSignal) {
  const id = attachmentIdFromUrl(wireUrl);
  if (!wireUrl.startsWith('/api/v1/attachments/') || !id) throw new Error('preview_unavailable');
  const response = await apiClient.getResponse(`/attachments/${id}/preview`, { signal });
  if (!response.body) throw new Error('preview_unavailable');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let text = '';
  let bytes = 0;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > 65536) throw new Error('preview_too_large');
      text += decoder.decode(value, { stream: true });
    }
    text += decoder.decode();
    if (!text.trim()) throw new Error('preview_empty');
    return { text, truncated: response.headers.get('X-Preview-Truncated') === 'true' };
  } finally {
    try {
      await reader.cancel();
    } finally {
      reader.releaseLock();
    }
  }
}
