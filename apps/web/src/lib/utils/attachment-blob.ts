/**
 * Authenticated attachment fetch for the document viewer.
 *
 * Same contract as `download-image.ts`: session cookie via
 * `credentials: 'include'`, binary blob out — apiClient consumes JSON and
 * cannot carry this. Throws on a non-OK status so the caller renders an
 * honest error instead of an empty document.
 */

export async function fetchAttachmentBlob(
  attachmentId: string,
  signal?: AbortSignal
): Promise<Blob> {
  const response = await fetch(`/api/v1/attachments/${attachmentId}`, {
    credentials: 'include',
    signal,
  });
  if (!response.ok) {
    throw new Error(`attachment fetch failed: ${response.status}`);
  }
  return response.blob();
}
