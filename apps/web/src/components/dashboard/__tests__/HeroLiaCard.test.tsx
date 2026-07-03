/**
 * HeroLiaCard — LLM greeting XSS boundary (audit wave 3, A4).
 *
 * The greeting is LLM output and can echo third-party text (e.g. a calendar
 * event titled "<img src=x onerror=alert(1)>"). It must render as
 * auto-escaped React children — never through dangerouslySetInnerHTML.
 */

import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';

import { HeroLiaCard } from '../HeroLiaCard';
import type { TextSection } from '@/types/briefing';

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
  useLiaGender: () => ({ liaImage: '/lia.png', toggleGender: vi.fn() }),
}));

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
