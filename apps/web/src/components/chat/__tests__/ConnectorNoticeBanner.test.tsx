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
    // Mixed actions on purpose: such a set is never condensed (no single
    // sentence would be true of both), so each notice keeps its own row.
    render(
      <ConnectorNoticeBanner
        notices={[notice(), notice({ connectorType: 'google_calendar', action: 'rate_limit' })]}
        onDismiss={onDismiss}
      />
    );

    const buttons = screen.getAllByRole('button', { name: 'chat.connector_notice.dismiss' });
    expect(buttons).toHaveLength(2);
    await userEvent.click(buttons[1]);

    expect(onDismiss).toHaveBeenCalledWith('google_calendar', 'rate_limit');
  });
});

/**
 * S4 — condensation. One expired Google refresh token invalidates Gmail,
 * Calendar and Drive at once: three amber rows, ~120 px of a band S0 measured
 * as already tight.
 */
describe('ConnectorNoticeBanner — condensation', () => {
  const threeReconnects = [
    notice({ connectorType: 'google_gmail' }),
    notice({ connectorType: 'google_calendar' }),
    notice({ connectorType: 'google_drive' }),
  ];

  it('collapses same-action notices into a single counted line', () => {
    render(<ConnectorNoticeBanner notices={threeReconnects} onDismiss={() => undefined} />);

    expect(screen.getByText('chat.connector_notice.summary_reconnect')).toBeInTheDocument();
    // The individual messages are not rendered while collapsed.
    expect(
      screen.queryByText('chat.connector_notice.reconnect_message:Gmail')
    ).not.toBeInTheDocument();
  });

  it('keeps ONE reconnect link on the summary — not one per connector', () => {
    render(<ConnectorNoticeBanner notices={threeReconnects} onDismiss={() => undefined} />);
    expect(
      screen.getAllByRole('link', { name: 'chat.connector_notice.reconnect_button' })
    ).toHaveLength(1);
  });

  it('reveals every notice on demand, each with its own dismiss control', async () => {
    render(<ConnectorNoticeBanner notices={threeReconnects} onDismiss={() => undefined} />);

    await userEvent.click(
      screen.getByRole('button', { name: 'chat.connector_notice.summary_expand' })
    );

    expect(screen.getByText('chat.connector_notice.reconnect_message:Gmail')).toBeInTheDocument();
    // 3 per-notice dismiss buttons + the group one.
    expect(screen.getAllByRole('button', { name: 'chat.connector_notice.dismiss' })).toHaveLength(
      4
    );
  });

  it('lets the group be dismissed WITHOUT expanding it', async () => {
    // Condensing the display must not cost a capability: the user could
    // dismiss each notice before, so the group must be dismissible too.
    const onDismiss = vi.fn();
    render(<ConnectorNoticeBanner notices={threeReconnects} onDismiss={onDismiss} />);

    await userEvent.click(screen.getByRole('button', { name: 'chat.connector_notice.dismiss' }));

    expect(onDismiss).toHaveBeenCalledTimes(3);
    expect(onDismiss).toHaveBeenCalledWith('google_gmail', 'reconnect');
    expect(onDismiss).toHaveBeenCalledWith('google_drive', 'reconnect');
  });

  it('exposes the expansion state to assistive technology', async () => {
    render(<ConnectorNoticeBanner notices={threeReconnects} onDismiss={() => undefined} />);

    const toggle = screen.getByRole('button', { name: 'chat.connector_notice.summary_expand' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(toggle);
    expect(
      screen.getByRole('button', { name: 'chat.connector_notice.summary_collapse' })
    ).toHaveAttribute('aria-expanded', 'true');
  });

  it('does not condense a single notice', () => {
    render(<ConnectorNoticeBanner notices={[notice()]} onDismiss={() => undefined} />);
    expect(screen.getByText('chat.connector_notice.reconnect_message:Gmail')).toBeInTheDocument();
    expect(screen.queryByText('chat.connector_notice.summary_reconnect')).not.toBeInTheDocument();
  });

  it('does not condense mixed actions', () => {
    render(
      <ConnectorNoticeBanner
        notices={[notice(), notice({ connectorType: 'google_drive', action: 'rate_limit' })]}
        onDismiss={() => undefined}
      />
    );
    expect(screen.queryByText('chat.connector_notice.summary_reconnect')).not.toBeInTheDocument();
    expect(screen.getByText('chat.connector_notice.reconnect_message:Gmail')).toBeInTheDocument();
    expect(
      screen.getByText('chat.connector_notice.rate_limit_message:Google Drive')
    ).toBeInTheDocument();
  });
});
