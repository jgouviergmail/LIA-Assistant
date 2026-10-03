/**
 * The landing video (ADR-330, amended): judged on what a visitor gets. No
 * section without a configured video; ONE `<video>` element the layout owns,
 * framed over the landing's slot, docked while its music plays with no slot
 * on the page, hidden when muted or paused with no slot, gone on a stop
 * route; sound and beats on a click or by default where the browser allows;
 * nothing left behind when the browser cannot play any rendition; several
 * videos played one after the other, each with its own credit and beats.
 */

import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// The player loads these two with `import()` once the sound plays. Imported
// here first, they are transformed while the file is collected, so the hook's
// `import()` resolves from the module cache: cold, under a full parallel run,
// the first transform outlasted `waitFor`'s second and the beat assertions
// failed now and then (measured 2026-10-02 and 2026-10-03, green alone).
import '@/lib/landing/beat-sync';
import '@/lib/landing/beats-schema';
import type { LandingVideoDescriptor } from '@/lib/landing/media';
import { PLAYER_RESUME_KEY } from '@/lib/landing/player-session';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';

import { LandingVideo, type LandingVideoSlotLabels } from '../LandingVideo';
import { LandingVideoHost, type LandingVideoHostLabels } from '../LandingVideoHost';

let pathname = '/fr';
vi.mock('next/navigation', () => ({
  usePathname: () => pathname,
}));

const HOST_LABELS: LandingVideoHostLabels = {
  ariaLabel: 'Illustration video',
  play: 'Play',
  pause: 'Pause',
  unmute: 'Sound on',
  mute: 'Sound off',
  nowPlaying: 'Video playing',
  backToVideo: 'Back to the video',
  close: 'Close the player',
};

const SLOT_LABELS: LandingVideoSlotLabels = {
  ariaLabel: 'Illustration video',
  aiDisclosure: 'AI-generated video',
  creditPrefix: 'Created by',
  externalLink: '(opens in a new window)',
};

const DESCRIPTOR: LandingVideoDescriptor = {
  poster: 'https://m.example.org/lia/clip-poster.webp',
  renditions: [
    {
      src: 'https://m.example.org/lia/clip-1080.av1.mp4',
      type: 'video/mp4; codecs="av01.0.08M.10"',
      minWidth: 900,
    },
    {
      src: 'https://m.example.org/lia/clip-1080.h264.mp4',
      type: 'video/mp4; codecs="avc1.640028"',
      minWidth: 900,
    },
    { src: 'https://m.example.org/lia/clip-720.h264.mp4', type: 'video/mp4; codecs="avc1.64001f"' },
  ],
  aspectRatio: [16, 9],
  durationSeconds: 306.48,
  hasBeats: true,
  credit: { label: '@someone', url: 'https://x.com/someone' },
  aiGenerated: true,
};

const BEATS = {
  version: 1,
  beats: [
    [0, 1, true],
    [464, 0.6, false],
  ],
};

/** The video that follows DESCRIPTOR in a playlist. */
const SECOND: LandingVideoDescriptor = {
  poster: 'https://m.example.org/lia/second-poster.webp',
  renditions: [
    {
      src: 'https://m.example.org/lia/second-720.av1.mp4',
      type: 'video/mp4; codecs="av01.0.05M.10"',
    },
    {
      src: 'https://m.example.org/lia/second-720.h264.mp4',
      type: 'video/mp4; codecs="avc1.64001f"',
    },
  ],
  aspectRatio: [16, 9],
  durationSeconds: 251.4,
  hasBeats: true,
  credit: { label: '@other', url: 'https://x.com/other' },
  aiGenerated: true,
};

const SECOND_BEATS = {
  version: 1,
  beats: [
    [100, 0.9, true],
    [580, 0.5, false],
  ],
};

const BEATS_OF = (rank: number) => `/api/landing-media/beats?video=${rank}`;

interface ObserverStub {
  options: IntersectionObserverInit | undefined;
  callback: IntersectionObserverCallback;
  elements: Element[];
}

let observers: ObserverStub[];
let fetchMock: ReturnType<typeof vi.fn>;
let play: ReturnType<typeof vi.spyOn>;
let pause: ReturnType<typeof vi.spyOn>;
let load: ReturnType<typeof vi.spyOn>;
let reducedMotion = false;

function jsonResponse(body: unknown, status = 200) {
  return { ok: status < 300, status, json: async () => body };
}

function stubFetch(video: LandingVideoDescriptor | null, next: LandingVideoDescriptor[] = []) {
  fetchMock = vi.fn(async (url: string) => {
    if (url === '/api/landing-media') return jsonResponse({ video, next });
    if (url === BEATS_OF(0)) return jsonResponse(BEATS);
    if (url === BEATS_OF(1) && next.length > 0) return jsonResponse(SECOND_BEATS);
    return jsonResponse({ error: 'not found' }, 404);
  });
  vi.stubGlobal('fetch', fetchMock);
}

/** The observer whose rootMargin reaches beyond the viewport ("near"). */
function nearObserver(): ObserverStub {
  const near = [...observers]
    .reverse()
    .find(o => (o.options?.rootMargin ?? '').includes('px') && o.options?.rootMargin !== '0px');
  if (!near) throw new Error('no "near" observer registered');
  return near;
}

/** The latest observer with no margin ("in view"). */
function viewObserver(): ObserverStub {
  const inView = [...observers]
    .reverse()
    .find(o => !o.options?.rootMargin || o.options.rootMargin === '0px');
  if (!inView) throw new Error('no "in view" observer registered');
  return inView;
}

function intersect(observer: ObserverStub, isIntersecting: boolean) {
  act(() => {
    observer.callback(
      observer.elements.map(target => ({ target, isIntersecting }) as IntersectionObserverEntry),
      {} as IntersectionObserver
    );
  });
}

function Tree({ slot }: { slot: boolean }) {
  return (
    <LandingVideoHost lng="fr" labels={HOST_LABELS}>
      {slot ? <LandingVideo labels={SLOT_LABELS} /> : null}
    </LandingVideoHost>
  );
}

async function renderMounted(
  video: LandingVideoDescriptor | null = DESCRIPTOR,
  next: LandingVideoDescriptor[] = []
) {
  stubFetch(video, next);
  const utils = render(<Tree slot />);
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith('/api/landing-media', expect.anything())
  );
  return utils;
}

/** The landing's own localized root — the default language carries no prefix. */
const BACK_HREF = `${buildLocalizedPath('/', 'fr')}#video`;

const videoElement = () => document.querySelector('video') as HTMLVideoElement;
const player = () => document.querySelector('[data-testid="landing-video-player"]');
const dock = () => screen.queryByRole('group', { name: HOST_LABELS.nowPlaying });

/**
 * The section, once the player stands over it: the slot registers in an
 * effect, the host mounts the player one render later, and its observers are
 * registered by its own effects — the section alone is not « mounted ».
 */
async function findMounted() {
  const section = await screen.findByRole('region', { name: SLOT_LABELS.ariaLabel });
  await waitFor(() => expect(player()).not.toBeNull());
  // The two observers are created by an effect AFTER the slot reaches the DOM:
  // under load the player was found first and the next lookup threw (1 run in
  // 12 with twelve coverage runs in parallel, 2026-10-02).
  await waitFor(() => {
    nearObserver();
    viewObserver();
  });
  return section;
}

/** Near and in view, started with the sound: the common opening of the playing scenarios. */
async function startedInView(next: LandingVideoDescriptor[] = []) {
  const utils = await renderMounted(DESCRIPTOR, next);
  await findMounted();
  intersect(nearObserver(), true);
  intersect(viewObserver(), true);
  await waitFor(() => expect(play).toHaveBeenCalledTimes(1));
  fireEvent.play(videoElement());
  return utils;
}

beforeEach(() => {
  observers = [];
  reducedMotion = false;
  pathname = '/fr';
  window.sessionStorage.clear();
  vi.stubGlobal(
    'IntersectionObserver',
    class {
      private readonly stub: ObserverStub;
      constructor(callback: IntersectionObserverCallback, options?: IntersectionObserverInit) {
        this.stub = { options, callback, elements: [] };
        observers.push(this.stub);
      }
      observe(element: Element) {
        this.stub.elements.push(element);
      }
      unobserve() {}
      disconnect() {}
    }
  );
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  );
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({
      matches: query.includes('prefers-reduced-motion') && reducedMotion,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      onchange: null,
      dispatchEvent: vi.fn(),
    }))
  );
  play = vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
  pause = vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined);
  load = vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => undefined);
  Object.defineProperty(window, 'innerWidth', { value: 1280, configurable: true, writable: true });
});

afterEach(() => {
  // Unmount while the media stubs still exist: the player pauses its video on
  // the way out, and jsdom's own `pause()` only reports « Not implemented ».
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('LandingVideo — without a configured video', () => {
  it('renders nothing at all, and the host mounts no player', async () => {
    const { container } = await renderMounted(null);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(container.querySelector('section')).toBeNull();
    expect(document.querySelector('video')).toBeNull();
    expect(player()).toBeNull();
  });
});

describe('LandingVideo — with a video, on the landing', () => {
  it('mounts the slot with the credit and the disclosure, and the player over it with the poster and no source yet', async () => {
    await renderMounted();
    const section = await findMounted();
    expect(section.id).toBe('video');
    // The element belongs to the host, not to the section: it is framed over the slot.
    expect(section.querySelector('video')).toBeNull();
    const video = videoElement();
    expect(player()).toHaveAttribute('data-mode', 'framed');
    expect(video.getAttribute('poster')).toBe(DESCRIPTOR.poster);
    // Sound is wanted by default: the element starts unmuted, the button says so.
    expect(video.muted).toBe(false);
    expect(screen.getByRole('button', { name: HOST_LABELS.mute })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    expect(video).toHaveAttribute('loop');
    expect(video).toHaveAttribute('playsinline');
    expect(video).toHaveAttribute('preload', 'none');
    expect(video.querySelectorAll('source')).toHaveLength(0);
    expect(play).not.toHaveBeenCalled();

    expect(within(section).getByText(SLOT_LABELS.aiDisclosure)).toBeInTheDocument();
    const credit = within(section).getByRole('link', { name: /@someone/ });
    expect(credit).toHaveAttribute('href', 'https://x.com/someone');
    expect(credit).toHaveAttribute('target', '_blank');
    expect(credit).toHaveAttribute('rel', expect.stringContaining('noopener'));
    expect(within(credit).getByText(SLOT_LABELS.externalLink)).toHaveClass('sr-only');
  });

  it('attaches the renditions the viewport is wide enough for when the slot comes near, and plays once in view', async () => {
    await renderMounted();
    await findMounted();
    intersect(nearObserver(), true);
    const video = videoElement();
    const sources = Array.from(video.querySelectorAll('source'));
    expect(sources.map(s => s.getAttribute('src'))).toEqual(DESCRIPTOR.renditions.map(r => r.src));
    expect(sources[0]).toHaveAttribute('type', 'video/mp4; codecs="av01.0.08M.10"');
    expect(video.preload).toBe('auto');
    expect(play).not.toHaveBeenCalled();

    intersect(viewObserver(), true);
    await waitFor(() => expect(play).toHaveBeenCalledTimes(1));
    expect(video.muted).toBe(false);
    // The beat map follows the sound actually playing, not the intent.
    expect(fetchMock).not.toHaveBeenCalledWith(BEATS_OF(0), expect.anything());
    fireEvent.play(video);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(BEATS_OF(0), expect.anything()));
    // The driver writes on the document, so every page's titles can read it.
    await waitFor(() => expect(document.documentElement.hasAttribute('data-beat')).toBe(true));
  });

  it('falls back to a muted start when the browser refuses the sound without a gesture', async () => {
    play
      .mockRejectedValueOnce(new DOMException('NotAllowedError', 'NotAllowedError'))
      .mockResolvedValue(undefined);
    await renderMounted();
    await findMounted();
    intersect(nearObserver(), true);
    intersect(viewObserver(), true);
    await waitFor(() => expect(play).toHaveBeenCalledTimes(2));
    expect(videoElement().muted).toBe(true);
    expect(screen.getByRole('button', { name: HOST_LABELS.unmute })).toHaveAttribute(
      'aria-pressed',
      'false'
    );
    expect(fetchMock).not.toHaveBeenCalledWith(BEATS_OF(0), expect.anything());
  });

  it('offers only the unrestricted renditions to a narrow viewport', async () => {
    Object.defineProperty(window, 'innerWidth', { value: 500, configurable: true, writable: true });
    await renderMounted();
    await findMounted();
    intersect(nearObserver(), true);
    const sources = Array.from(videoElement().querySelectorAll('source'));
    expect(sources.map(s => s.getAttribute('src'))).toEqual([
      'https://m.example.org/lia/clip-720.h264.mp4',
    ]);
  });

  it('does not start on its own for a reader who asked for less motion', async () => {
    reducedMotion = true;
    await renderMounted();
    await findMounted();
    intersect(nearObserver(), true);
    intersect(viewObserver(), true);
    expect(videoElement().querySelectorAll('source').length).toBeGreaterThan(0);
    expect(play).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: HOST_LABELS.play }));
    expect(play).toHaveBeenCalledTimes(1);
  });

  it('pauses a muted video that leaves the view and resumes it when it comes back', async () => {
    play
      .mockRejectedValueOnce(new DOMException('NotAllowedError', 'NotAllowedError'))
      .mockResolvedValue(undefined);
    await renderMounted();
    await findMounted();
    intersect(nearObserver(), true);
    intersect(viewObserver(), true);
    await waitFor(() => expect(play).toHaveBeenCalledTimes(2));
    const video = videoElement();
    expect(video.muted).toBe(true);
    fireEvent.play(video);

    intersect(viewObserver(), false);
    expect(pause).toHaveBeenCalledTimes(1);
    fireEvent.pause(video);
    expect(dock()).toBeNull();

    intersect(viewObserver(), true);
    await waitFor(() => expect(play).toHaveBeenCalledTimes(3));
  });

  it('lets the visitor pause and resume, and remembers a pause across the scroll', async () => {
    await startedInView();
    const video = videoElement();

    fireEvent.click(screen.getByRole('button', { name: HOST_LABELS.pause }));
    expect(pause).toHaveBeenCalledTimes(1);
    fireEvent.pause(video);

    intersect(viewObserver(), false);
    intersect(viewObserver(), true);
    expect(play).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: HOST_LABELS.play }));
    expect(play).toHaveBeenCalledTimes(2);
  });

  it('starts with the sound when the browser allows it, docks when scrolled away, and a click mutes it', async () => {
    await startedInView();
    const video = videoElement();

    expect(video.muted).toBe(false);
    expect(screen.getByRole('button', { name: HOST_LABELS.mute })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(BEATS_OF(0), expect.anything()));

    intersect(viewObserver(), false);
    expect(pause).not.toHaveBeenCalled();
    const docked = await screen.findByRole('group', { name: HOST_LABELS.nowPlaying });
    expect(player()).toHaveAttribute('data-mode', 'docked');
    expect(within(docked).getByRole('link', { name: HOST_LABELS.backToVideo })).toHaveAttribute(
      'href',
      BACK_HREF
    );

    fireEvent.click(within(docked).getByRole('button', { name: HOST_LABELS.pause }));
    expect(pause).toHaveBeenCalledTimes(1);
    fireEvent.pause(video);
    await waitFor(() => expect(dock()).toBeNull());
    // Paused with a frame on the page: back in its frame, off-screen, not hidden.
    expect(player()).toHaveAttribute('data-mode', 'framed');

    intersect(viewObserver(), true);
    expect(player()).toHaveAttribute('data-mode', 'framed');
    fireEvent.click(screen.getByRole('button', { name: HOST_LABELS.mute }));
    expect(video.muted).toBe(true);
    expect(screen.getByRole('button', { name: HOST_LABELS.unmute })).toHaveAttribute(
      'aria-pressed',
      'false'
    );
  });

  it('removes the section and the player when the browser can play no rendition', async () => {
    await renderMounted();
    await findMounted();
    intersect(nearObserver(), true);
    fireEvent.error(videoElement());
    await waitFor(() =>
      expect(screen.queryByRole('region', { name: SLOT_LABELS.ariaLabel })).toBeNull()
    );
    expect(document.querySelector('video')).toBeNull();
  });

  it('keeps the poster and the play button when the browser refuses to autoplay', async () => {
    play.mockRejectedValue(new DOMException('NotAllowedError', 'NotAllowedError'));
    await renderMounted();
    await findMounted();
    intersect(nearObserver(), true);
    intersect(viewObserver(), true);
    // With the sound, then muted: both refused.
    await waitFor(() => expect(play).toHaveBeenCalledTimes(2));
    expect(screen.getByRole('button', { name: HOST_LABELS.play })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: SLOT_LABELS.ariaLabel })).toBeInTheDocument();
  });
});

describe('LandingVideo — across the pages', () => {
  it('keeps the SAME element playing, docked, when the landing leaves with the sound on', async () => {
    const { rerender } = await startedInView();
    const video = videoElement();
    load.mockClear();

    rerender(<Tree slot={false} />);
    expect(screen.queryByRole('region', { name: SLOT_LABELS.ariaLabel })).toBeNull();
    expect(videoElement()).toBe(video);
    expect(pause).not.toHaveBeenCalled();
    expect(load).not.toHaveBeenCalled();
    const docked = await screen.findByRole('group', { name: HOST_LABELS.nowPlaying });
    expect(player()).toHaveAttribute('data-mode', 'docked');
    expect(within(docked).getByRole('link', { name: HOST_LABELS.backToVideo })).toHaveAttribute(
      'href',
      BACK_HREF
    );
    expect(within(docked).getByRole('button', { name: HOST_LABELS.close })).toBeInTheDocument();
  });

  it('hides and pauses a muted video that has no slot, with no dock', async () => {
    play
      .mockRejectedValueOnce(new DOMException('NotAllowedError', 'NotAllowedError'))
      .mockResolvedValue(undefined);
    const { rerender } = await renderMounted();
    await findMounted();
    intersect(nearObserver(), true);
    intersect(viewObserver(), true);
    await waitFor(() => expect(play).toHaveBeenCalledTimes(2));
    const video = videoElement();
    fireEvent.play(video);

    rerender(<Tree slot={false} />);
    expect(pause).toHaveBeenCalledTimes(1);
    fireEvent.pause(video);
    expect(dock()).toBeNull();
    expect(player()).toHaveAttribute('data-mode', 'hidden');
    expect(videoElement()).toBe(video);
  });

  it('frames the element again when a slot comes back, and resumes it in view', async () => {
    const { rerender } = await startedInView();
    const video = videoElement();
    rerender(<Tree slot={false} />);
    await screen.findByRole('group', { name: HOST_LABELS.nowPlaying });

    rerender(<Tree slot />);
    await findMounted();
    expect(videoElement()).toBe(video);
    expect(player()).toHaveAttribute('data-mode', 'framed');
    expect(dock()).toBeNull();
    expect(pause).not.toHaveBeenCalled();
  });

  it('closing the dock is the visitor pausing: hidden, and no autoplay back in the frame', async () => {
    const { rerender } = await startedInView();
    const video = videoElement();
    rerender(<Tree slot={false} />);
    const docked = await screen.findByRole('group', { name: HOST_LABELS.nowPlaying });

    fireEvent.click(within(docked).getByRole('button', { name: HOST_LABELS.close }));
    expect(pause).toHaveBeenCalledTimes(1);
    fireEvent.pause(video);
    await waitFor(() => expect(dock()).toBeNull());
    expect(player()).toHaveAttribute('data-mode', 'hidden');

    rerender(<Tree slot />);
    await findMounted();
    intersect(viewObserver(), true);
    expect(play).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: HOST_LABELS.play })).toBeInTheDocument();
  });

  it('stops and leaves the DOM on a stop route, pausing first', async () => {
    const { rerender } = await startedInView();
    rerender(<Tree slot={false} />);
    await screen.findByRole('group', { name: HOST_LABELS.nowPlaying });

    pathname = '/fr/login';
    rerender(<Tree slot={false} />);
    expect(pause).toHaveBeenCalledTimes(1);
    expect(document.querySelector('video')).toBeNull();
    expect(player()).toBeNull();
    expect(dock()).toBeNull();
  });

  it('writes a resume record when it unmounts and resumes from it on a fresh mount', async () => {
    const { unmount } = await startedInView();
    const video = videoElement();
    Object.defineProperty(video, 'currentTime', {
      value: 42.5,
      configurable: true,
      writable: true,
    });
    unmount();
    const stored = JSON.parse(window.sessionStorage.getItem(PLAYER_RESUME_KEY) ?? 'null');
    expect(stored).toMatchObject({ time: 42.5, sound: true });

    observers = [];
    play.mockClear();
    await renderMounted();
    await findMounted();
    const fresh = videoElement();
    expect(fresh).not.toBe(video);
    intersect(nearObserver(), true);
    // The position is applied once the metadata is there, and the sound stays on.
    Object.defineProperty(fresh, 'currentTime', { value: 0, configurable: true, writable: true });
    fireEvent.loadedMetadata(fresh);
    expect(fresh.currentTime).toBe(42.5);
    intersect(viewObserver(), true);
    await waitFor(() => expect(play).toHaveBeenCalledTimes(1));
    expect(fresh.muted).toBe(false);
  });

  it('ignores a resume record older than the bound', async () => {
    window.sessionStorage.setItem(
      PLAYER_RESUME_KEY,
      JSON.stringify({ time: 42.5, sound: false, at: Date.now() - 10 * 60_000 })
    );
    await renderMounted();
    await findMounted();
    const fresh = videoElement();
    intersect(nearObserver(), true);
    Object.defineProperty(fresh, 'currentTime', { value: 0, configurable: true, writable: true });
    fireEvent.loadedMetadata(fresh);
    expect(fresh.currentTime).toBe(0);
    expect(fresh.muted).toBe(false);
  });
});

/** The `src` of every `<source>` the element holds. */
const sourceUrls = () =>
  Array.from(videoElement().querySelectorAll('source')).map(s => s.getAttribute('src'));

/** What the end of a non-looping element fires: a pause, then `ended`. */
function endCurrent(video: HTMLVideoElement) {
  fireEvent.pause(video);
  fireEvent.ended(video);
}

describe('LandingVideo — a playlist', () => {
  it('loops a single video, and lets one of several end', async () => {
    await renderMounted();
    await findMounted();
    expect(videoElement()).toHaveAttribute('loop');
    cleanup();

    observers = [];
    await renderMounted(DESCRIPTOR, [SECOND]);
    await findMounted();
    expect(videoElement()).not.toHaveAttribute('loop');
  });

  it('hands the SAME element the next video when one ends: its sources, its poster, its credit, its beats, the sound kept', async () => {
    await startedInView([SECOND]);
    const video = videoElement();
    const section = screen.getByRole('region', { name: SLOT_LABELS.ariaLabel });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(BEATS_OF(0), expect.anything()));
    await waitFor(() => expect(document.documentElement.hasAttribute('data-beat')).toBe(true));
    const loads = load.mock.calls.length;

    endCurrent(video);

    await waitFor(() => expect(sourceUrls()).toEqual(SECOND.renditions.map(r => r.src)));
    expect(videoElement()).toBe(video);
    expect(video.getAttribute('poster')).toBe(SECOND.poster);
    expect(load.mock.calls.length).toBe(loads + 1);
    // It plays on by itself, with the sound it had: the visitor clicked nothing.
    await waitFor(() => expect(play).toHaveBeenCalledTimes(2));
    expect(video.muted).toBe(false);
    expect(within(section).getByRole('link', { name: /@other/ })).toHaveAttribute(
      'href',
      'https://x.com/other'
    );
    expect(within(section).queryByRole('link', { name: /@someone/ })).toBeNull();
    // The titles stop with the first video and follow the second's map once it plays.
    expect(document.documentElement.hasAttribute('data-beat')).toBe(false);
    fireEvent.play(video);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(BEATS_OF(1), expect.anything()));
    await waitFor(() => expect(document.documentElement.hasAttribute('data-beat')).toBe(true));
  });

  it('comes back to the first video after the last, and starts over', async () => {
    await startedInView([SECOND]);
    const video = videoElement();
    endCurrent(video);
    await waitFor(() => expect(sourceUrls()).toEqual(SECOND.renditions.map(r => r.src)));
    fireEvent.play(video);

    endCurrent(video);
    await waitFor(() => expect(sourceUrls()).toEqual(DESCRIPTOR.renditions.map(r => r.src)));
    expect(video.getAttribute('poster')).toBe(DESCRIPTOR.poster);
    await waitFor(() => expect(play).toHaveBeenCalledTimes(3));
    expect(screen.getByRole('link', { name: /@someone/ })).toBeInTheDocument();
  });

  it('resumes a fresh mount in the video it left, at its time, ONCE: the next video starts at its first frame', async () => {
    const { unmount } = await startedInView([SECOND]);
    const video = videoElement();
    endCurrent(video);
    await waitFor(() => expect(sourceUrls()).toEqual(SECOND.renditions.map(r => r.src)));
    fireEvent.play(video);
    Object.defineProperty(video, 'currentTime', { value: 12, configurable: true, writable: true });
    unmount();
    const stored = JSON.parse(window.sessionStorage.getItem(PLAYER_RESUME_KEY) ?? 'null');
    expect(stored).toMatchObject({ video: 1, time: 12, sound: true });

    observers = [];
    play.mockClear();
    await renderMounted(DESCRIPTOR, [SECOND]);
    await findMounted();
    const fresh = videoElement();
    expect(fresh.getAttribute('poster')).toBe(SECOND.poster);
    expect(screen.getByRole('link', { name: /@other/ })).toBeInTheDocument();
    intersect(nearObserver(), true);
    expect(sourceUrls()).toEqual(SECOND.renditions.map(r => r.src));
    Object.defineProperty(fresh, 'currentTime', { value: 0, configurable: true, writable: true });
    fireEvent.loadedMetadata(fresh);
    expect(fresh.currentTime).toBe(12);

    intersect(viewObserver(), true);
    await waitFor(() => expect(play).toHaveBeenCalledTimes(1));
    fireEvent.play(fresh);
    endCurrent(fresh);
    await waitFor(() => expect(sourceUrls()).toEqual(DESCRIPTOR.renditions.map(r => r.src)));
    fresh.currentTime = 0;
    fireEvent.loadedMetadata(fresh);
    expect(fresh.currentTime).toBe(0);
  });

  it('starts at the first video when a resume record names a rank the list does not hold', async () => {
    window.sessionStorage.setItem(
      PLAYER_RESUME_KEY,
      JSON.stringify({ video: 3, time: 42.5, sound: true, at: Date.now() })
    );
    await renderMounted(DESCRIPTOR, [SECOND]);
    await findMounted();
    const fresh = videoElement();
    expect(fresh.getAttribute('poster')).toBe(DESCRIPTOR.poster);
    intersect(nearObserver(), true);
    Object.defineProperty(fresh, 'currentTime', { value: 0, configurable: true, writable: true });
    fireEvent.loadedMetadata(fresh);
    expect(fresh.currentTime).toBe(0);
  });

  it('reads an answer cached before playlists (the video alone) as one looping video', async () => {
    fetchMock = vi.fn(async (url: string) =>
      url === '/api/landing-media'
        ? jsonResponse({ video: DESCRIPTOR })
        : jsonResponse({ error: 'not found' }, 404)
    );
    vi.stubGlobal('fetch', fetchMock);
    render(<Tree slot />);
    await findMounted();
    expect(videoElement()).toHaveAttribute('loop');
  });
});
