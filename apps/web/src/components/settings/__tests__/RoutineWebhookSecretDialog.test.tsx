/**
 * RoutineWebhookSecretDialog — a routine's address and the secret just drawn,
 * shown this once (ADR-386).
 *
 * The oracle is what the person reads and what the page lets escape: the
 * address, the secret and the signed-call example are shown whole, and nothing
 * carrying the secret is offered to the selection assist, which would hand a
 * selection to a model. Geometry at phone width is proven in the browser
 * (`e2e/smoke/routine-webhook-secret.spec.ts`), never by a class name here.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { RoutineWebhookSecretDialog } from '../RoutineWebhookSecretDialog';

const DRAWN = {
  webhook_url: 'https://lia.example.org/api/v1/hooks/routines/pA9xK2mQ7vR4tY1wZ8bN3cL6',
  webhook_secret: 'xQ3m-Zr8_vK2pL9tY6wB1nH4cF7dJ0sA5eG2uR8iO3k', // gitleaks:allow
};

beforeEach(() => vi.clearAllMocks());

describe('RoutineWebhookSecretDialog', () => {
  it('stays closed until a secret is drawn', () => {
    renderWithProviders(<RoutineWebhookSecretDialog drawn={null} onClose={vi.fn()} />);

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('shows the address, the secret and a signed call, each whole', () => {
    renderWithProviders(<RoutineWebhookSecretDialog drawn={DRAWN} onClose={vi.fn()} />);

    const dialog = screen.getByRole('dialog', { name: 'scheduled_actions.webhook.secret_title' });
    expect(
      screen.getByRole('group', { name: 'scheduled_actions.webhook.address' })
    ).toHaveTextContent(DRAWN.webhook_url);
    expect(
      screen.getByRole('group', { name: 'scheduled_actions.webhook.secret' })
    ).toHaveTextContent(DRAWN.webhook_secret);
    const example = screen.getByRole('figure', { name: 'scheduled_actions.webhook.example' });
    expect(example).toHaveTextContent(DRAWN.webhook_secret);
    expect(dialog).toContainElement(example);
  });

  it('offers nothing that carries the secret to the selection assist', () => {
    renderWithProviders(<RoutineWebhookSecretDialog drawn={DRAWN} onClose={vi.fn()} />);

    const carriers = screen
      .getAllByText((_content, element) =>
        Boolean(element?.textContent?.includes(DRAWN.webhook_secret) && !element.children.length)
      )
      .filter(element => element.closest('[role="dialog"]'));
    expect(carriers.length).toBeGreaterThanOrEqual(2);
    for (const carrier of carriers) {
      expect(carrier.closest('[data-selection-assist="off"]')).not.toBeNull();
    }
  });

  it('closes on the explicit « copied »', async () => {
    const onClose = vi.fn();
    const { user } = renderWithProviders(
      <RoutineWebhookSecretDialog drawn={DRAWN} onClose={onClose} />
    );

    await user.click(screen.getByRole('button', { name: 'scheduled_actions.webhook.done' }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
