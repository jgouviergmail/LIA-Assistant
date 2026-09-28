import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import { InteractiveChatMockup } from '../InteractiveChatMockup';
import { ProductScene } from '../demo/ProductScene';
import { PRODUCT_DEMO_KEY as KEY, PRODUCT_SCENES } from '../demo/scenes';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';

const locale = vi.hoisted(() => ({ language: 'keys' }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      if (locale.language === 'keys') return key;
      let value: unknown = locale.language === 'fr' ? fr : en;
      for (const part of key.split('.')) {
        if (typeof value !== 'object' || value === null || !(part in value)) return key;
        value = Reflect.get(value, part);
      }
      return typeof value === 'string' ? value : key;
    },
  }),
}));
vi.mock('next/link', () => ({
  default: ({ children, href, ...props }: React.ComponentProps<'a'> & { href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

let setVisible: (visible: boolean) => void;
let motion = false;
const disconnect = vi.fn();
function advance(ms: number) {
  act(() => vi.advanceTimersByTime(ms));
}

beforeEach(() => {
  locale.language = 'keys';
  motion = false;
  vi.useFakeTimers();
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: query === '(prefers-reduced-motion: reduce)' && motion,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
  vi.stubGlobal(
    'IntersectionObserver',
    class implements IntersectionObserver {
      root = null;
      rootMargin = '0px';
      scrollMargin = '0px';
      thresholds = [0.15];
      constructor(callback: IntersectionObserverCallback) {
        setVisible = visible =>
          callback(
            [
              {
                isIntersecting: visible,
                target: document.body,
                intersectionRatio: visible ? 1 : 0,
                boundingClientRect: new DOMRect(),
                intersectionRect: new DOMRect(),
                rootBounds: null,
                time: 0,
              },
            ],
            this
          );
      }
      observe() {
        setVisible(true);
      }
      unobserve() {}
      disconnect = disconnect;
      takeRecords() {
        return [];
      }
    }
  );
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('InteractiveChatMockup', () => {
  it('lets a keyboard user select a scene without moving focus', async () => {
    vi.useRealTimers();
    motion = true;
    const user = userEvent.setup();
    render(<InteractiveChatMockup lng="fr" />);
    await user.tab();
    expect(screen.getByRole('button', { name: `${KEY}.scenes.decision.title` })).toHaveFocus();
    await user.tab();
    await user.keyboard('{Enter}');
    expect(screen.getByRole('button', { name: `${KEY}.scenes.day.title` })).toHaveFocus();
    expect(screen.getByText(`${KEY}.scenes.day.request`)).toBeVisible();
  });
  it('offers six contextual scenarios and keeps the selected result available to read', () => {
    render(<InteractiveChatMockup lng="fr" />);
    const group = screen.getByRole('group', { name: `${KEY}.choose_scene` });
    expect(within(group).getAllByRole('button')).toHaveLength(6);
    fireEvent.click(screen.getByRole('button', { name: `${KEY}.scenes.research.title` }));
    expect(screen.getByText(`${KEY}.scenes.research.request`)).toBeVisible();
    expect(screen.getByText(`${KEY}.scenes.research.result_title`)).not.toBeVisible();
    advance(1700);
    advance(2400);
    expect(screen.getByText(`${KEY}.scenes.research.result_title`)).toBeVisible();
    advance(60000);
    expect(screen.getByRole('button', { name: `${KEY}.scenes.research.title` })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    expect(screen.getByText(`${KEY}.scenes.research.result_title`)).toBeVisible();
    expect(screen.getByRole('button', { name: `${KEY}.play` })).toBeInTheDocument();
  });

  it('pauses and replays the selected scene without losing keyboard focus', () => {
    render(<InteractiveChatMockup lng="fr" />);
    const pause = screen.getByRole('button', { name: `${KEY}.pause` });
    pause.focus();
    fireEvent.click(pause);
    advance(10000);
    expect(pause).toHaveFocus();
    expect(screen.getByText(`${KEY}.context`)).not.toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: `${KEY}.play` }));
    advance(1700);
    expect(screen.getByText(`${KEY}.context`)).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: `${KEY}.replay` }));
    expect(screen.getByText(`${KEY}.context`)).not.toBeVisible();
  });

  it('stops progressing off screen and cleans up on unmount', () => {
    const { unmount } = render(<InteractiveChatMockup lng="fr" />);
    act(() => setVisible(false));
    advance(10000);
    expect(screen.getByText(`${KEY}.context`)).not.toBeVisible();
    act(() => setVisible(true));
    advance(1700);
    expect(screen.getByText(`${KEY}.context`)).toBeVisible();
    unmount();
    expect(vi.getTimerCount()).toBe(0);
    expect(disconnect).toHaveBeenCalled();
  });

  it('starts a fresh reading interval when replay is used during the first step', () => {
    render(<InteractiveChatMockup lng="fr" />);
    advance(1200);
    fireEvent.click(screen.getByRole('button', { name: `${KEY}.replay` }));
    advance(600);
    expect(screen.getByText(`${KEY}.context`)).not.toBeVisible();
    advance(1100);
    expect(screen.getByText(`${KEY}.context`)).toBeVisible();
  });

  it('keeps a completed scene in place when its active selector is clicked again', () => {
    render(<InteractiveChatMockup lng="fr" />);
    advance(1700);
    advance(2400);
    fireEvent.click(screen.getByRole('button', { name: `${KEY}.scenes.decision.title` }));
    expect(screen.getByText(`${KEY}.scenes.decision.result_title`)).toBeVisible();
    expect(screen.getByRole('button', { name: `${KEY}.play` })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: `${KEY}.replay` }));
    expect(screen.getByText(`${KEY}.scenes.decision.result_title`)).not.toBeVisible();
  });

  it('shows static complete scenes with reduced motion and never schedules an animation', () => {
    motion = true;
    render(<InteractiveChatMockup lng="fr" withCta={false} />);
    for (const scene of PRODUCT_SCENES) {
      fireEvent.click(screen.getByRole('button', { name: scene.titleKey }));
      expect(screen.getByText(scene.outcomeKey)).toBeVisible();
      expect(screen.getByText(`${KEY}.scenes.${scene.id}.guardrail`)).toBeVisible();
    }
    expect(screen.queryByRole('button', { name: `${KEY}.pause` })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: `${KEY}.replay` })).not.toBeInTheDocument();
    expect(vi.getTimerCount()).toBe(0);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('provides the register CTA on the dedicated demo and opt-in explanations', () => {
    render(<InteractiveChatMockup lng="fr" />);
    expect(screen.getByRole('link', { name: 'landing.hero.cta_primary' })).toHaveAttribute(
      'href',
      buildLocalizedPath('/register', 'fr')
    );
    expect(screen.getByText(`${KEY}.scenes.decision.difference`)).not.toBeVisible();
    fireEvent.click(screen.getByText(`${KEY}.difference`));
    expect(screen.getByText(`${KEY}.scenes.decision.difference`)).toBeVisible();
  });

  it.each([
    ['fr', 'Choisir une situation', 'Mettre en pause', 'Rejouer la démonstration'],
    ['en', 'Choose a situation', 'Pause the demonstration', 'Replay the demonstration'],
  ])('localizes the accessible controls in %s', (language, group, pause, replay) => {
    locale.language = language;
    render(<InteractiveChatMockup lng={language} />);
    expect(screen.getByRole('group', { name: group })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: pause })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: replay })).toBeInTheDocument();
  });
});

describe('ProductScene', () => {
  it.each(PRODUCT_SCENES)(
    'uses the same completed scene for the $id chapter illustration',
    scene => {
      render(<ProductScene sceneId={scene.id} />);
      expect(screen.getByText(`${KEY}.scenes.${scene.id}.request`)).toBeVisible();
      expect(screen.getByText(scene.outcomeKey)).toBeVisible();
      expect(screen.getByText(`${KEY}.illustrative`)).toBeVisible();
      expect(screen.queryByRole('button')).not.toBeInTheDocument();
    }
  );
});
