/** Native-only JPEG bridge; the selected file has already been previewed locally. */
import { nativeImageBridge } from './shell';
const MAX_BYTES = 2 * 1024 * 1024;
export type PhotoShareOutcome = 'offered' | 'cancelled' | 'unsupported';
function supported(value: unknown): boolean {
  if (!value || typeof value !== 'object' || !('capabilities' in value)) return false;
  const caps = value.capabilities;
  return !!caps && typeof caps === 'object' && 'shareImage' in caps && caps.shareImage === 1;
}
async function supportsPhoto(bridge: ReturnType<typeof nativeImageBridge>): Promise<boolean> {
  if (!bridge) return false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const result = await Promise.race([
      bridge.get(),
      new Promise<null>(resolve => {
        timer = setTimeout(() => resolve(null), 1500);
      }),
    ]);
    return supported(result);
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}
export function nativePhotoAvailable(): Promise<boolean> {
  return supportsPhoto(nativeImageBridge());
}
function validateFile(file: File, isCurrent: () => boolean) {
  if (
    !isCurrent() ||
    file.name !== 'lia-world-photo.jpg' ||
    file.type !== 'image/jpeg' ||
    file.size === 0 ||
    file.size > MAX_BYTES
  )
    throw new Error('world_photo_native_input');
}
function outcome(result: unknown): PhotoShareOutcome {
  if (
    result &&
    typeof result === 'object' &&
    'status' in result &&
    (result.status === 'offered' || result.status === 'cancelled')
  )
    return result.status;
  throw new Error('world_photo_native_outcome');
}
export async function shareNativePhoto(
  file: File,
  isCurrent: () => boolean
): Promise<PhotoShareOutcome> {
  const bridge = nativeImageBridge();
  if (!bridge || !(await supportsPhoto(bridge))) return 'unsupported';
  validateFile(file, isCurrent);
  const bytes = new Uint8Array(await file.arrayBuffer());
  if (!isCurrent()) throw new Error('world_photo_native_owner');
  let binary = '';
  // Avoid a multi-megabyte argument list or repeated whole-file concatenation.
  for (let start = 0; start < bytes.length; start += 8192)
    binary += String.fromCharCode(...bytes.subarray(start, start + 8192));
  const result = await bridge.shareImage({
    base64: btoa(binary),
    mimeType: 'image/jpeg',
    filename: 'lia-world-photo.jpg',
  });
  return outcome(result);
}
