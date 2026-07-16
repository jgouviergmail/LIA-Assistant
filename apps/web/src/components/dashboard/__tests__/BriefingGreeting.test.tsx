/**
 * Render tests for BriefingGreeting — renders the greeting sentence and only
 * mounts the LLMUsageBadge when usage data is present. Uses the global
 * react-i18next mock (from the test setup): t echoes the key, so the badge's
 * presence is detected via its token-label i18n key.
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { BriefingGreeting } from '../BriefingGreeting';
import type { TextSection } from '@/types/briefing';

function section(over: Partial<TextSection> = {}): TextSection {
  return { text: 'Bonjour Jean', ...over } as TextSection;
}

describe('BriefingGreeting', () => {
  it('renders the greeting sentence', () => {
    render(<BriefingGreeting greeting={section()} />);
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Bonjour Jean');
  });

  it('omits the usage badge when no usage is present', () => {
    render(<BriefingGreeting greeting={section({ usage: undefined })} />);
    expect(screen.queryByText('dashboard.briefing.usage_tokens')).toBeNull();
  });

  it('mounts the usage badge when usage is present', () => {
    render(
      <BriefingGreeting
        greeting={section({
          usage: {
            tokens_in: 1,
            tokens_out: 2,
            tokens_cache: 0,
            cost_eur: 0.0001,
            model_name: 'x',
          },
        })}
      />
    );
    expect(screen.getByText('dashboard.briefing.usage_tokens')).toBeInTheDocument();
  });
});
