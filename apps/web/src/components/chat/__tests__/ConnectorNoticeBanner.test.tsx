/**
 * ConnectorNoticeBanner — actionable connector failure banners (Lot 3 P3).
 *
 * Oracles: role/name and visible state. A reconnect notice shows the message
 * with the human connector label and a link to the connectors settings; a
 * rate-limit notice has no link; dismiss fires the callback with the exact
 * (connector, action) pair. Renders nothing without notices.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ConnectorNoticeBanner } from '@/components/chat/ConnectorNoticeBanner';
import type { ConnectorNotice } from '@/types/chat-state';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts?.connector ? `${key}:${opts.connector}` : key,
    i18n: { language: 'fr' },
  }),
}));

function notice(overrides: Partial<ConnectorNotice> = {}): ConnectorNotice {
  return {
    connectorType: 'google_gmail',
    action: 'reconnect',
    toolName: 'search_emails_tool',
    ...overrides,
  };
}

describe('ConnectorNoticeBanner', () => {
  it('renders nothing without notices', () => {
    const { container } = render(
      <ConnectorNoticeBanner notices={[]} onDismiss={() => undefined} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the reconnect message with the human connector label and settings link', () => {
    render(<ConnectorNoticeBanner notices={[notice()]} onDismiss={() => undefined} />);

    // CONNECTOR_LABELS resolves google_gmail → "Gmail".
    expect(screen.getByText('chat.connector_notice.reconnect_message:Gmail')).toBeInTheDocument();
    const link = screen.getByRole('link', { name: 'chat.connector_notice.reconnect_button' });
    expect(link).toHaveAttribute('href', '/fr/dashboard/settings?section=connectors');
  });

  it('shows the rate-limit message without a reconnect link', () => {
    render(
      <ConnectorNoticeBanner
        notices={[notice({ action: 'rate_limit' })]}
        onDismiss={() => undefined}
      />
    );

    expect(screen.getByText('chat.connector_notice.rate_limit_message:Gmail')).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('falls back to the raw connector type for an unknown connector', () => {
    render(
      <ConnectorNoticeBanner
        notices={[notice({ connectorType: 'unknown_thing' })]}
        onDismiss={() => undefined}
      />
    );

    expect(
      screen.getByText('chat.connector_notice.reconnect_message:unknown_thing')
    ).toBeInTheDocument();
  });

  it('dismiss fires with the exact (connector, action) pair', async () => {
    const onDismiss = vi.fn();
    render(
      <ConnectorNoticeBanner
        notices={[notice(), notice({ connectorType: 'google_calendar' })]}
        onDismiss={onDismiss}
      />
    );

    const buttons = screen.getAllByRole('button', { name: 'chat.connector_notice.dismiss' });
    expect(buttons).toHaveLength(2);
    await userEvent.click(buttons[1]);

    expect(onDismiss).toHaveBeenCalledWith('google_calendar', 'reconnect');
  });
});
