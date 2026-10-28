import { afterEach, expect, it, vi } from 'vitest';
import { nativePhotoAvailable, shareNativePhoto } from '../photo';
function shell(get: unknown, shareImage = vi.fn().mockResolvedValue({ status: 'offered' })) {
  Reflect.set(window, 'Capacitor', {
    isNativePlatform: () => true,
    Plugins: { LiaShell: { get, shareImage } },
  });
  return shareImage;
}
afterEach(() => Reflect.deleteProperty(window, 'Capacitor'));
it('requires a positive native capability instead of trusting a proxy method', async () => {
  expect(await nativePhotoAvailable()).toBe(false);
  const share = shell(vi.fn().mockResolvedValue({ url: 'https://example.invalid' }));
  expect(await nativePhotoAvailable()).toBe(false);
  expect(
    await shareNativePhoto(
      new File(['x'], 'lia-world-photo.jpg', { type: 'image/jpeg' }),
      () => true
    )
  ).toBe('unsupported');
  expect(share).not.toHaveBeenCalled();
});
it('shares bounded preview bytes only after checking the current owner again', async () => {
  const share = shell(vi.fn().mockResolvedValue({ capabilities: { shareImage: 1 } }));
  expect(await nativePhotoAvailable()).toBe(true);
  const file = new File([new Uint8Array([255, 216, 255, 217])], 'lia-world-photo.jpg', {
    type: 'image/jpeg',
  });
  expect(await shareNativePhoto(file, () => true)).toBe('offered');
  expect(share).toHaveBeenCalledWith({
    base64: '/9j/2Q==',
    mimeType: 'image/jpeg',
    filename: 'lia-world-photo.jpg',
  });
  share.mockClear();
  await expect(shareNativePhoto(file, () => false)).rejects.toThrow();
  expect(share).not.toHaveBeenCalled();
  await expect(
    shareNativePhoto(
      new File([new Uint8Array(2 * 1024 * 1024 + 1)], 'lia-world-photo.jpg', {
        type: 'image/jpeg',
      }),
      () => true
    )
  ).rejects.toThrow();
});
it('does not accept an unknown native outcome as successful publication', async () => {
  shell(
    vi.fn().mockResolvedValue({ capabilities: { shareImage: 1 } }),
    vi.fn().mockResolvedValue({ status: 'published' })
  );
  await expect(
    shareNativePhoto(new File(['jpeg'], 'lia-world-photo.jpg', { type: 'image/jpeg' }), () => true)
  ).rejects.toThrow();
});
it('withdraws a file whose owner changes while reading its bytes', async () => {
  const share = shell(vi.fn().mockResolvedValue({ capabilities: { shareImage: 1 } }));
  let current = true;
  const file = new File(['jpeg'], 'lia-world-photo.jpg', { type: 'image/jpeg' });
  vi.spyOn(file, 'arrayBuffer').mockImplementation(async () => {
    current = false;
    return new ArrayBuffer(4);
  });
  await expect(shareNativePhoto(file, () => current)).rejects.toThrow('owner');
  expect(share).not.toHaveBeenCalled();
});
it('bounds capability probing when an older bridge hangs or rejects', async () => {
  vi.useFakeTimers();
  try {
    shell(() => new Promise(() => {}));
    const pending = nativePhotoAvailable();
    await vi.advanceTimersByTimeAsync(1500);
    expect(await pending).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
    shell(vi.fn().mockRejectedValue(new Error('old binary')));
    expect(await nativePhotoAvailable()).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
  } finally {
    vi.useRealTimers();
  }
});
it('rejects invalid preview metadata without sending native data and preserves cancellation', async () => {
  const share = shell(vi.fn().mockResolvedValue({ capabilities: { shareImage: 1 } }));
  for (const file of [
    new File(['x'], '../private.jpg', { type: 'image/jpeg' }),
    new File(['x'], 'lia-world-photo.jpg', { type: 'image/png' }),
    new File([], 'lia-world-photo.jpg', { type: 'image/jpeg' }),
  ]) {
    await expect(shareNativePhoto(file, () => true)).rejects.toThrow('input');
  }
  expect(share).not.toHaveBeenCalled();
  share.mockResolvedValueOnce({ status: 'cancelled' });
  expect(
    await shareNativePhoto(
      new File(['x'], 'lia-world-photo.jpg', { type: 'image/jpeg' }),
      () => true
    )
  ).toBe('cancelled');
});
