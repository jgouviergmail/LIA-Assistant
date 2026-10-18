import { describe, it, expect, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import { ClassificationBadges, classificationAttentionStyle } from '../ClassificationBadges';
import { MarkdownContent } from '../MarkdownContent';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
const now = Date.now();
const value = {
  version: 'email-event-v1-phishing',
  kind: 'email',
  category: 'phishing_scam',
  priority: 'critical',
  evidence_scope: 'snippet',
  evaluated_at: new Date(now).toISOString(),
  valid_until: new Date(now + 300000).toISOString(),
};

describe('closed JEV badges', () => {
  it('removes live urgency when validity ends without replaying a native call', () => {
    vi.useFakeTimers();
    vi.setSystemTime(now);
    try {
      render(
        <ClassificationBadges
          value={{ ...value, valid_until: new Date(now + 1000).toISOString() }}
        />
      );
      expect(screen.getByText('classification.critical')).toBeInTheDocument();
      act(() => {
        vi.advanceTimersByTime(1001);
      });
      expect(screen.queryByText('classification.critical')).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
  it('shows independent category and priority with stable text and no live alert', () => {
    const { container } = render(<ClassificationBadges value={value} />);
    expect(screen.getByText('classification.phishing_scam')).toBeInTheDocument();
    expect(screen.getByText('classification.critical')).toBeInTheDocument();
    expect(container.querySelector('[role="alert"]')).toBeNull();
    expect(container.querySelector('a')).toBeNull();
  });
  it('renders neither unknown nor normal and rejects malformed/extra fields', () => {
    const { container, rerender } = render(
      <ClassificationBadges value={{ ...value, category: 'unknown', priority: 'normal' }} />
    );
    expect(container).toBeEmptyDOMElement();
    rerender(<ClassificationBadges value={{ ...value, category: '<img src=x>' }} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<ClassificationBadges value={{ ...value, injected: true }} />);
    expect(container).toBeEmptyDOMElement();
  });
  it('never restarts historical attention and bounds a remount to the remaining time', () => {
    expect(classificationAttentionStyle(new Date(now - 10000).toISOString(), now)).toEqual({});
    expect(classificationAttentionStyle(new Date(now - 2000).toISOString(), now)).toEqual({
      animation: 'classification-attention 1s ease-in-out 4',
      animationDelay: '-2s',
    });
    expect(classificationAttentionStyle('invalid', now)).toEqual({});
    expect(classificationAttentionStyle(new Date(now + 1000).toISOString(), now)).toEqual({});
  });
  it('preserves a server badge through the real HTML sanitizer with historical attention stopped', () => {
    const { container } = render(
      <MarkdownContent
        content={
          '<div class="lia-classification"><span class="content-classification-badge content-classification-badge--phishing" data-classified-at="2020-01-01T00:00:00Z"><span aria-hidden="true">⚠</span>Phishing/Arnaque</span></div>'
        }
      />
    );
    expect(screen.getByText('Phishing/Arnaque')).toBeInTheDocument();
    expect(container.querySelector('.content-classification-badge')).not.toHaveStyle({
      animation: 'classification-attention 1s ease-in-out 4',
    });
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });
});
