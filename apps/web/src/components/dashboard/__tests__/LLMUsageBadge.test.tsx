/**
 * Render tests for LLMUsageBadge — the compact "tokens · cost" strip on the
 * briefing. Verifies the token total, locale-formatted cost, the i18n token
 * label interpolation, and the tooltip (incl. the model-name fallback). The
 * i18n mock echoes the key + params so interpolation is assertable.
 */
import { describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts
        ? `${key}|${Object.entries(opts)
            .map(([k, v]) => `${k}=${v}`)
            .join('|')}`
        : key,
    i18n: { language: 'fr' },
  }),
}));

import { LLMUsageBadge } from '../LLMUsageBadge';
import type { LLMUsage } from '@/types/briefing';

function usage(over: Partial<LLMUsage> = {}): LLMUsage {
  return {
    tokens_in: 100,
    tokens_out: 50,
    tokens_cache: 10,
    cost_eur: 0.001234,
    model_name: 'gpt-4',
    ...over,
  } as LLMUsage;
}

describe('LLMUsageBadge', () => {
  it('sums the token total and interpolates the label', () => {
    const { container } = render(<LLMUsageBadge usage={usage()} />);
    const text = container.textContent ?? '';
    expect(text).toContain('count=160'); // 100 + 50 + 10
    expect(text).toContain('formatted=160');
  });

  it('renders the locale-formatted cost (6 decimals, fr)', () => {
    const { container } = render(<LLMUsageBadge usage={usage()} />);
    expect(container.textContent).toContain('0,001234');
  });

  it('carries a tooltip with per-bucket breakdown and the model name', () => {
    const { container } = render(<LLMUsageBadge usage={usage()} />);
    const title = (container.firstChild as HTMLElement).getAttribute('title') ?? '';
    expect(title).toContain('tokens_in=100');
    expect(title).toContain('model=gpt-4');
  });

  it('falls back to an em dash when the model name is absent', () => {
    const { container } = render(<LLMUsageBadge usage={usage({ model_name: null })} />);
    const title = (container.firstChild as HTMLElement).getAttribute('title') ?? '';
    expect(title).toContain('model=—');
  });

  it('applies an extra className when provided', () => {
    const { container } = render(<LLMUsageBadge usage={usage()} className="extra-cls" />);
    expect((container.firstChild as HTMLElement).className).toContain('extra-cls');
  });
});
