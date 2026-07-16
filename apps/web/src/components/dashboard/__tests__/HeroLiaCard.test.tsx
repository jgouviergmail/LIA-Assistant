/**
 * HeroLiaCard — LLM greeting XSS boundary (audit wave 3, A4) and
 * keyboard-operable avatar toggle (audit F045).
 *
 * The greeting is LLM output and can echo third-party text (e.g. a calendar
 * event titled "<img src=x onerror=alert(1)>"). It must render as
 * auto-escaped React children — never through dangerouslySetInnerHTML.
 * The avatar toggle used to be a mouse-only Card onClick; it must be a real,
 * named button reachable and operable with the keyboard.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent } from '@testing-library/react';

import { HeroLiaCard } from '../HeroLiaCard';
import type { TextSection } from '@/types/briefing';

const { mockToggleGender } = vi.hoisted(() => ({ mockToggleGender: vi.fn() }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'fr' } }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

// Render the avatar as a span so <img> assertions only see greeting content
vi.mock('next/image', () => ({
  default: ({ alt }: { alt: string }) => <span data-testid="lia-avatar">{alt}</span>,
}));

vi.mock('@/hooks/useLiaGender', () => ({
  useLiaGender: () => ({ liaImage: '/lia.png', toggleGender: mockToggleGender }),
}));

beforeEach(() => {
  mockToggleGender.mockClear();
});

function makeGreeting(text: string): TextSection {
  return { text, generated_at: '2026-07-03T08:00:00Z', usage: null };
}

describe('HeroLiaCard — greeting is inert', () => {
  it('renders a hostile event title as literal text (no element injection)', () => {
    const payload = '<img src=x onerror=alert(1)> Bonjour Jérôme';
    const { container } = render(<HeroLiaCard greeting={makeGreeting(payload)} />);

    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('[onerror]')).toBeNull();
    // The markup appears as visible text, exactly as the LLM emitted it
    expect(container.textContent).toContain('<img src=x onerror=alert(1)>');
    expect(container.textContent).toContain('Bonjour Jérôme');
  });

  it('does not execute script tags echoed in the greeting', () => {
    const { container } = render(
      <HeroLiaCard greeting={makeGreeting('Bonjour <script>window.hacked = true;</script>')} />
    );

    expect(container.querySelector('script')).toBeNull();
    expect((window as unknown as { hacked?: boolean }).hacked).toBeUndefined();
  });

  it('renders a plain greeting normally', () => {
    const { container } = render(
      <HeroLiaCard greeting={makeGreeting('Bonjour Jérôme, journée chargée !')} />
    );

    expect(container.textContent).toContain('Bonjour Jérôme, journée chargée !');
  });
});

describe('HeroLiaCard — avatar toggle is keyboard-accessible (F045)', () => {
  it('exposes the toggle as a real, named button', () => {
    const { getByLabelText } = render(<HeroLiaCard />);
    const toggle = getByLabelText('dashboard.actions.toggle_avatar');
    expect(toggle.tagName).toBe('BUTTON');
    expect(toggle.getAttribute('type')).toBe('button');
  });

  it('activates with a click (mouse behavior preserved)', () => {
    const { getByLabelText } = render(<HeroLiaCard />);
    fireEvent.click(getByLabelText('dashboard.actions.toggle_avatar'));
    expect(mockToggleGender).toHaveBeenCalledTimes(1);
  });

  it('is focusable and never nests the CTA buttons (valid interactive tree)', () => {
    const { getByLabelText } = render(<HeroLiaCard />);
    const toggle = getByLabelText('dashboard.actions.toggle_avatar') as HTMLButtonElement;

    toggle.focus();
    expect(document.activeElement).toBe(toggle);
    // A <button> must never contain other interactive elements — the CTA
    // buttons are siblings, not descendants.
    expect(toggle.querySelector('button, a, input')).toBeNull();
  });
});
