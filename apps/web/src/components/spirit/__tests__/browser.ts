import { vi } from 'vitest';

/** jsdom cannot measure intersections; notify the real observer callback. */
export class SpiritIntersectionObserver implements IntersectionObserver {
  static instances: SpiritIntersectionObserver[] = [];
  readonly root = null;
  readonly rootMargin = '0px';
  readonly scrollMargin = '0px';
  readonly thresholds = [0];
  readonly targets = new Set<Element>();
  readonly disconnect = vi.fn(() => this.targets.clear());
  constructor(readonly callback: IntersectionObserverCallback) {
    SpiritIntersectionObserver.instances.push(this);
  }
  observe(target: Element) {
    this.targets.add(target);
  }
  unobserve(target: Element) {
    this.targets.delete(target);
  }
  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }
  notify(target: Element, visible: boolean) {
    const rect = target.getBoundingClientRect();
    this.callback(
      [
        {
          target,
          time: 0,
          rootBounds: null,
          boundingClientRect: rect,
          intersectionRect: rect,
          intersectionRatio: visible ? 1 : 0,
          isIntersecting: visible,
        },
      ],
      this
    );
  }
}

export function installSpiritBrowser(reducedMotion = false) {
  let visibility: DocumentVisibilityState = 'visible';
  type MotionListener = EventListenerOrEventListenerObject | ((event: MediaQueryListEvent) => void);
  const callbacks = new Set<MotionListener>();
  const media = {
    matches: reducedMotion,
    media: '(prefers-reduced-motion: reduce)',
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(() => true),
    addEventListener: vi.fn((_type: string, callback: MotionListener) => {
      callbacks.add(callback);
    }),
    removeEventListener: vi.fn((_type: string, callback: MotionListener) => {
      callbacks.delete(callback);
    }),
  };
  vi.spyOn(window, 'matchMedia').mockImplementation(query =>
    query.includes('prefers-reduced-motion')
      ? media
      : {
          ...media,
          matches: false,
          media: query,
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
        }
  );
  vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => visibility);
  SpiritIntersectionObserver.instances = [];
  vi.stubGlobal('IntersectionObserver', SpiritIntersectionObserver);
  return {
    media,
    setMotion(value: boolean) {
      media.matches = value;
      const event = Object.assign(new Event('change'), { matches: value, media: media.media });
      callbacks.forEach(callback =>
        typeof callback === 'function' ? callback(event) : callback.handleEvent(event)
      );
    },
    setVisibility(value: DocumentVisibilityState) {
      visibility = value;
      document.dispatchEvent(new Event('visibilitychange'));
    },
  };
}

export function showSpirit(container: HTMLElement, visible = true) {
  const target = container.querySelector('[data-spirit-avatar]');
  if (!target) throw new Error('The avatar has no visibility target');
  const observer = SpiritIntersectionObserver.instances.find(instance =>
    instance.targets.has(target)
  );
  if (!observer) throw new Error('The avatar is not being observed');
  observer.notify(target, visible);
}
