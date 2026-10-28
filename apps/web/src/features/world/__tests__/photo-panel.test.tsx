import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { Activity, StrictMode } from 'react';
import { WorldPhotoPanel } from '../WorldPhotoPanel';
import { canShareWorldPhoto, renderPhoto, shareWorldPhoto, type PhotoImage } from '../photo-export';
import { projectPhotoScene } from '../photo-projection';
import { WORLD } from '../definition';
import { createSimulation } from '../simulation';
import { createCamera } from '../geometry';
import { NEUTRAL_ATMOSPHERE } from '../atmosphere';

vi.mock('@/i18n/client', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('../photo-export', async original => ({
  ...(await original<typeof import('../photo-export')>()),
  renderPhoto: vi.fn(),
  canShareWorldPhoto: vi.fn().mockReturnValue(true),
  shareWorldPhoto: vi.fn().mockResolvedValue('offered'),
}));
afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});
function photo(): PhotoImage {
  return { blob: new Blob(['jpeg'], { type: 'image/jpeg' }), width: 1600, height: 900 };
}
function setup() {
  vi.mocked(canShareWorldPhoto).mockReturnValue(true);
  const originalURL = URL;
  const create = vi
    .fn()
    .mockReturnValueOnce('blob:photo-one')
    .mockReturnValueOnce('blob:photo-two');
  const revoke = vi.fn();
  vi.stubGlobal(
    'URL',
    class extends originalURL {
      static createObjectURL = create;
      static revokeObjectURL = revoke;
    }
  );
  const sim = createSimulation(WORLD);
  const scene = projectPhotoScene({
    player: sim.player,
    bip: sim.bip,
    camera: createCamera({ width: 1000, height: 700 }, WORLD.spawn),
    time: 0,
    season: 'neutral',
    atmosphere: NEUTRAL_ATMOSPHERE,
    home: null,
  });
  return { create, revoke, scene };
}
it('starts only the surviving StrictMode effect and never overlaps the native encoder', async () => {
  const { scene } = setup();
  vi.mocked(renderPhoto).mockResolvedValue(photo());
  render(
    <StrictMode>
      <WorldPhotoPanel lng="fr" ownerId="owner" scene={scene} />
    </StrictMode>
  );
  await screen.findByRole('img');
  expect(renderPhoto).toHaveBeenCalledOnce();
});
it('keeps the signature mandatory instead of offering an opt-out', async () => {
  const { scene } = setup();
  vi.mocked(renderPhoto).mockResolvedValue(photo());
  render(<WorldPhotoPanel lng="fr" ownerId="owner" scene={scene} />);
  await screen.findByRole('img');
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
});
it('prepares a preview without sharing and keeps the old image during an explicit format refresh', async () => {
  const { scene, create, revoke } = setup();
  let finish: ((image: PhotoImage) => void) | undefined;
  vi.mocked(renderPhoto)
    .mockResolvedValueOnce(photo())
    .mockImplementationOnce(
      () =>
        new Promise(resolve => {
          finish = resolve;
        })
    );
  const ui = render(<WorldPhotoPanel lng="fr" ownerId="owner" scene={scene} />);
  const image = await screen.findByRole('img', { name: 'world.photo.preview' });
  expect(shareWorldPhoto).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'world.photo.portrait' }));
  expect(screen.getByRole('img')).toBe(image);
  expect(screen.getByRole('button', { name: 'world.photo.share' })).toHaveAttribute(
    'aria-disabled',
    'true'
  );
  expect(revoke).not.toHaveBeenCalled();
  await waitFor(() => expect(finish).toBeDefined());
  await act(async () => {
    if (!finish) throw new Error('No pending encoding');
    finish({ ...photo(), width: 1280, height: 1600 });
  });
  await waitFor(() => expect(create).toHaveBeenCalledTimes(2));
  expect(revoke).toHaveBeenCalledWith('blob:photo-one');
  fireEvent.click(screen.getByRole('button', { name: 'world.photo.share' }));
  await waitFor(() => expect(shareWorldPhoto).toHaveBeenCalledOnce());
  ui.unmount();
  expect(revoke).toHaveBeenCalledWith('blob:photo-two');
});
it('never creates a URL from a late render after the owner or panel lifetime ends', async () => {
  const { scene, create } = setup();
  let finish: ((image: PhotoImage) => void) | undefined;
  vi.mocked(renderPhoto).mockImplementationOnce(
    () =>
      new Promise(resolve => {
        finish = resolve;
      })
  );
  const ui = render(<WorldPhotoPanel lng="fr" ownerId="owner" scene={scene} />);
  await waitFor(() => expect(finish).toBeDefined());
  ui.unmount();
  await act(async () => {
    if (!finish) throw new Error('No pending encoding');
    finish(photo());
  });
  expect(create).not.toHaveBeenCalled();
});
it('shows a bounded encoding failure and retries only after a fresh owner action', async () => {
  const { scene } = setup();
  vi.mocked(renderPhoto)
    .mockRejectedValueOnce(new Error('world_photo_encode'))
    .mockResolvedValueOnce(photo());
  render(<WorldPhotoPanel lng="fr" ownerId="owner" scene={scene} />);
  expect(await screen.findByRole('alert')).toHaveTextContent('world.photo.error');
  expect(renderPhoto).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole('button', { name: 'world.photo.retry' }));
  await screen.findByRole('img');
  expect(renderPhoto).toHaveBeenCalledTimes(2);
});
it('never shares twice while the chooser is pending and reports cancellation truthfully', async () => {
  const { scene } = setup();
  vi.mocked(renderPhoto).mockResolvedValue(photo());
  let finish: ((result: 'cancelled') => void) | undefined;
  vi.mocked(shareWorldPhoto).mockImplementationOnce(
    () =>
      new Promise(resolve => {
        finish = resolve;
      })
  );
  render(<WorldPhotoPanel lng="fr" ownerId="owner" scene={scene} />);
  const share = await screen.findByRole('button', { name: 'world.photo.share' });
  fireEvent.click(share);
  fireEvent.click(share);
  expect(shareWorldPhoto).toHaveBeenCalledOnce();
  expect(share).toHaveAttribute('aria-disabled', 'true');
  const download = screen.getByRole('link', { name: 'world.photo.download' });
  expect(fireEvent.click(download)).toBe(false);
  fireEvent.click(screen.getByRole('button', { name: 'world.photo.portrait' }));
  expect(renderPhoto).toHaveBeenCalledOnce();
  await act(async () => {
    if (!finish) throw new Error('No chooser');
    finish('cancelled');
  });
  expect(screen.getByRole('status')).toHaveTextContent('world.photo.cancelled');
  let prevented: boolean | undefined;
  document.addEventListener(
    'click',
    event => {
      prevented = event.defaultPrevented;
      event.preventDefault();
    },
    { once: true }
  );
  fireEvent.click(download);
  expect(prevented).toBe(false);
});
it('retains a usable previous preview after a failed refresh and names a refused share', async () => {
  const { scene } = setup();
  vi.mocked(renderPhoto).mockResolvedValueOnce(photo()).mockRejectedValueOnce(new Error('encode'));
  render(<WorldPhotoPanel lng="fr" ownerId="owner" scene={scene} />);
  const image = await screen.findByRole('img');
  fireEvent.click(screen.getByRole('button', { name: 'world.photo.portrait' }));
  await screen.findByRole('alert');
  expect(screen.getByRole('img')).toBe(image);
  expect(screen.getByRole('alert')).toHaveTextContent('world.photo.previous');
  vi.mocked(shareWorldPhoto).mockRejectedValueOnce(new Error('denied'));
  fireEvent.click(screen.getByRole('button', { name: 'world.photo.share' }));
  await waitFor(() =>
    expect(screen.getByRole('status')).toHaveTextContent('world.photo.share_error')
  );
});
it('offers the positively detected native backend when browser file sharing is unavailable', async () => {
  const { scene } = setup();
  vi.mocked(canShareWorldPhoto).mockReturnValue(false);
  vi.mocked(renderPhoto).mockResolvedValue(photo());
  Reflect.set(window, 'Capacitor', {
    isNativePlatform: () => true,
    Plugins: {
      LiaShell: {
        get: vi.fn().mockResolvedValue({ capabilities: { shareImage: 1 } }),
        shareImage: vi.fn(),
      },
    },
  });
  try {
    render(<WorldPhotoPanel lng="fr" ownerId="owner" scene={scene} />);
    const button = await screen.findByRole('button', { name: 'world.photo.share' });
    fireEvent.click(button);
    await waitFor(() =>
      expect(shareWorldPhoto).toHaveBeenCalledWith(expect.any(File), expect.any(Function), true)
    );
  } finally {
    Reflect.deleteProperty(window, 'Capacitor');
  }
});
it('withdraws a native share before handoff when its preview closes during capability probing', async () => {
  const { scene } = setup();
  vi.mocked(canShareWorldPhoto).mockReturnValue(false);
  vi.mocked(renderPhoto).mockResolvedValue(photo());
  const capability = { capabilities: { shareImage: 1 } };
  let release: ((value: typeof capability) => void) | undefined;
  const get = vi
    .fn()
    .mockResolvedValueOnce(capability)
    .mockImplementationOnce(
      () =>
        new Promise(resolve => {
          release = resolve;
        })
    );
  const native = vi.fn().mockResolvedValue({ status: 'offered' });
  Reflect.set(window, 'Capacitor', {
    isNativePlatform: () => true,
    Plugins: { LiaShell: { get, shareImage: native } },
  });
  const actual = await vi.importActual<typeof import('../photo-export')>('../photo-export');
  vi.mocked(shareWorldPhoto).mockImplementationOnce(actual.shareWorldPhoto);
  try {
    const ui = render(<WorldPhotoPanel lng="fr" ownerId="owner" scene={scene} />);
    fireEvent.click(await screen.findByRole('button', { name: 'world.photo.share' }));
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    ui.unmount();
    await act(async () => {
      if (!release) throw new Error('No pending native probe');
      release(capability);
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    expect(native).not.toHaveBeenCalled();
  } finally {
    Reflect.deleteProperty(window, 'Capacitor');
  }
});
it('keeps the next owner preview when a previous owner renderer resolves late', async () => {
  const { scene, create } = setup();
  let finish: ((image: PhotoImage) => void) | undefined;
  vi.mocked(renderPhoto)
    .mockImplementationOnce(
      () =>
        new Promise(resolve => {
          finish = resolve;
        })
    )
    .mockResolvedValueOnce({ ...photo(), width: 1280, height: 1600 });
  const ui = render(<WorldPhotoPanel lng="fr" ownerId="first-owner" scene={scene} />);
  await waitFor(() => expect(finish).toBeDefined());
  ui.rerender(<WorldPhotoPanel lng="fr" ownerId="next-owner" scene={scene} />);
  const image = await screen.findByRole('img');
  expect(image).toHaveAttribute('height', '1600');
  await act(async () => {
    if (!finish) throw new Error('No old renderer');
    finish(photo());
  });
  expect(create).toHaveBeenCalledOnce();
  expect(screen.getByRole('img')).toBe(image);
  expect(image).toHaveAttribute('height', '1600');
});
it('never shows a revoked preview after a reveal, and never encodes the same still twice', async () => {
  const { scene, create, revoke } = setup();
  vi.mocked(renderPhoto).mockResolvedValue(photo());
  const panel = (mode: 'visible' | 'hidden') => (
    <Activity mode={mode}>
      <WorldPhotoPanel lng="fr" ownerId="owner" scene={scene} />
    </Activity>
  );
  const view = render(panel('visible'));
  const download = await screen.findByRole('link', { name: 'world.photo.download' });
  expect(download).toHaveAttribute('href', 'blob:photo-one');
  view.rerender(panel('hidden'));
  expect(revoke).toHaveBeenCalledExactlyOnceWith('blob:photo-one');
  view.rerender(panel('visible'));
  await waitFor(() =>
    expect(screen.getByRole('link', { name: 'world.photo.download' })).toHaveAttribute(
      'href',
      'blob:photo-two'
    )
  );
  expect(screen.getByRole('img')).toHaveAttribute('src', 'blob:photo-two');
  expect(create).toHaveBeenCalledTimes(2);
  expect(revoke).not.toHaveBeenCalledWith('blob:photo-two');
  expect(renderPhoto).toHaveBeenCalledOnce();
  view.unmount();
  expect(revoke).toHaveBeenLastCalledWith('blob:photo-two');
});
