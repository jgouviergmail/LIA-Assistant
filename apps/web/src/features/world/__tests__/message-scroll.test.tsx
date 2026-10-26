import { act, fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import { WorldMessageList } from '../WorldMessageList';
import type { WorldMessage } from '../message-protocol';
import { MessageScrollStore } from '../message-scroll-store';

vi.mock('@/i18n/client', () => ({
  useTranslation: (lng: 'en' | 'fr') => ({
    t: (key: string) => {
      let value: unknown = lng === 'fr' ? fr : en;
      for (const part of key.split('.'))
        value = value && typeof value === 'object' ? Reflect.get(value, part) : undefined;
      return typeof value === 'string' ? value : key;
    },
  }),
}));
const message = (id: string): WorldMessage => ({
  id,
  sender_id: 'peer',
  sender_alias: 'Peer',
  recipient_id: 'owner',
  recipient_alias: 'You',
  outgoing: false,
  original: id,
  text: id,
  language: 'fr',
  status: 'original',
  created_at: 1000,
  expires_at: 2800,
  receipt: null,
});

it.each([
  ['en', 'Latest messages'],
  ['fr', 'Derniers messages'],
] as const)(
  'keeps scrollback and offers a keyboard-usable path to new messages in %s',
  (lng, action) => {
    const first = [message('first')];
    const props = { lng, tokensVisible: false, canTranslate: false, onTranslate: vi.fn() };
    const view = render(<WorldMessageList {...props} messages={first} />);
    const log = screen.getByRole('log');
    Object.defineProperties(log, {
      scrollHeight: { configurable: true, value: 1000 },
      clientHeight: { configurable: true, value: 200 },
    });
    log.scrollTop = 100;
    fireEvent.scroll(log);
    view.rerender(<WorldMessageList {...props} messages={[...first, message('new arrival')]} />);
    expect(log.scrollTop).toBe(100);
    const latest = screen.getByRole('button', { name: action });
    latest.focus();
    fireEvent.click(latest);
    expect(log.scrollTop).toBe(1000);
    expect(log).toHaveFocus();
    expect(screen.queryByRole('button', { name: action })).not.toBeInTheDocument();
  }
);

it('follows arrivals when already reading at the bottom', () => {
  const props = {
    lng: 'en' as const,
    tokensVisible: false,
    canTranslate: false,
    onTranslate: vi.fn(),
  };
  const view = render(<WorldMessageList {...props} messages={[]} />);
  const log = screen.getByRole('log');
  Object.defineProperties(log, {
    scrollHeight: { configurable: true, value: 900 },
    clientHeight: { configurable: true, value: 200 },
  });
  view.rerender(<WorldMessageList {...props} messages={[message('first')]} />);
  expect(log.scrollTop).toBe(900);
});

it('keeps the latest messages in view after resizing, without moving a reader in history', () => {
  let resize = () => {};
  const disconnect = vi.fn();
  vi.stubGlobal(
    'ResizeObserver',
    class {
      constructor(callback: () => void) {
        resize = callback;
      }
      observe() {}
      disconnect() {
        resize = () => {};
        disconnect();
      }
    }
  );
  try {
    const view = render(
      <WorldMessageList
        lng="en"
        messages={[message('first')]}
        tokensVisible={false}
        canTranslate={false}
        onTranslate={vi.fn()}
      />
    );
    const log = screen.getByRole('log');
    Object.defineProperties(log, {
      scrollHeight: { configurable: true, value: 1000 },
      clientHeight: { configurable: true, value: 200 },
    });
    act(() => resize());
    expect(log.scrollTop).toBe(1000);
    log.scrollTop = 100;
    fireEvent.scroll(log);
    act(() => resize());
    expect(log.scrollTop).toBe(100);
    view.unmount();
    expect(disconnect).toHaveBeenCalled();
  } finally {
    vi.unstubAllGlobals();
  }
});

it('restores the same owner reading position after private content is remounted', () => {
  const scrollStore = new MessageScrollStore();
  const props = {
    lng: 'en' as const,
    messages: [message('first'), message('second')],
    tokensVisible: false,
    canTranslate: false,
    onTranslate: vi.fn(),
    scrollStore,
  };
  const view = render(<WorldMessageList {...props} />);
  const log = screen.getByRole('log');
  Object.defineProperties(log, {
    scrollHeight: { configurable: true, value: 1000 },
    clientHeight: { configurable: true, value: 200 },
  });
  log.scrollTop = 120;
  fireEvent.scroll(log);
  // Hiding a private portal can reset its browser scroll metrics. That is not
  // a new reading position chosen by its owner.
  Object.defineProperty(log, 'clientHeight', { configurable: true, value: 0 });
  log.scrollTop = 0;
  fireEvent.scroll(log);
  view.unmount();
  render(<WorldMessageList {...props} />);
  expect(screen.getByRole('log').scrollTop).toBe(120);
  expect(screen.getByRole('button', { name: 'Latest messages' })).toBeVisible();
});

it('preserves scrollback when a portal is still unconstrained after its first animation frame', () => {
  const scrollStore = new MessageScrollStore();
  scrollStore.remember({ anchored: false, top: 120 });
  const original = Object.getOwnPropertyDescriptor(Element.prototype, 'scrollTop');
  const positions = new WeakMap<object, number>();
  let ready = false;
  let frame: FrameRequestCallback | undefined;
  let resize: (() => void) | undefined;
  vi.stubGlobal(
    'ResizeObserver',
    class {
      constructor(callback: () => void) {
        resize = callback;
      }
      observe() {}
      disconnect() {}
    }
  );
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    frame = callback;
    return 1;
  });
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
  Object.defineProperty(Element.prototype, 'scrollTop', {
    configurable: true,
    get() {
      return positions.get(this) ?? 0;
    },
    set(value: number) {
      positions.set(this, ready ? value : 0);
    },
  });
  try {
    const view = render(
      <WorldMessageList
        lng="en"
        messages={[message('first')]}
        tokensVisible={false}
        canTranslate={false}
        onTranslate={vi.fn()}
        scrollStore={scrollStore}
      />
    );
    expect(screen.getByRole('log').scrollTop).toBe(0);
    const log = screen.getByRole('log');
    Object.defineProperties(log, {
      scrollHeight: { configurable: true, value: 1000 },
      clientHeight: { configurable: true, value: 200 },
    });
    act(() => frame?.(0));
    fireEvent.scroll(log);
    expect(scrollStore.read()).toEqual({ anchored: false, top: 120 });
    ready = true;
    act(() => resize?.());
    expect(log.scrollTop).toBe(120);
    expect(scrollStore.read()).toEqual({ anchored: false, top: 120 });
    view.unmount();
  } finally {
    if (original) Object.defineProperty(Element.prototype, 'scrollTop', original);
    vi.unstubAllGlobals();
  }
});
