/**
 * NtfySettings — the ntfy block of the notification settings (ADR-391).
 *
 * Oracle: what the person sees for each state the API reports, and what each control asks the
 * hook — never the markup. Text is read as KEYS through a stable stub that writes its
 * interpolations (`key(name=value)`), so a reason mapped to the wrong outcome fails here;
 * `ntfy-labels.test.ts` holds every key to the six locales.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import type { AppConfig } from '@/hooks/useAppConfig';
import type {
  NtfyActionResult,
  NtfyOverview,
  NtfySubscriptionView,
  useNtfySubscriptions as UseNtfySubscriptions,
} from '@/hooks/useNtfySubscriptions';

type Hook = ReturnType<typeof UseNtfySubscriptions>;

const { useNtfySubscriptions, useAppConfig, useApplicationAccountQuery, toast } = vi.hoisted(
  () => ({
    useNtfySubscriptions: vi.fn(),
    useAppConfig: vi.fn(),
    useApplicationAccountQuery: vi.fn(),
    toast: { success: vi.fn(), error: vi.fn() },
  })
);
vi.mock('@/hooks/useNtfySubscriptions', async importOriginal => ({
  ...(await importOriginal<typeof import('@/hooks/useNtfySubscriptions')>()),
  useNtfySubscriptions,
}));
vi.mock('@/hooks/useAppConfig', () => ({ useAppConfig }));
vi.mock('@/hooks/useApplicationAccountQuery', () => ({ useApplicationAccountQuery }));
vi.mock('sonner', () => ({ toast }));
const { i18n } = vi.hoisted(() => {
  const write = (key: string, options?: Record<string, unknown>): string =>
    options && Object.keys(options).length > 0
      ? `${key}(${Object.entries(options)
          .map(([name, value]) => `${name}=${String(value)}`)
          .join(',')})`
      : key;
  // One identity for the whole file: `t` sits in effect dependencies (setup.ts).
  return { i18n: { t: write, i18n: { language: 'en', changeLanguage: () => undefined } } };
});
vi.mock('@/i18n/client', () => ({ useTranslation: () => i18n }));

import { NtfySettings } from '../NtfySettings';

const KEY = 'settings.notifications.ntfy';
/** What the stub writes for a key of the ntfy settings, with its interpolations. */
function k(key: string, options?: Record<string, unknown>): string {
  return i18n.t(`${KEY}.${key}`, options);
}

function view(overrides: Partial<NtfySubscriptionView> = {}): NtfySubscriptionView {
  return {
    id: 'sub-1',
    server_kind: 'instance',
    server_url: 'https://ntfy.example.org',
    topic: 'lia_AbCdEfGhIjKlMnOpQrStUvWxYz12',
    has_token: false,
    content: 'minimal',
    is_active: true,
    last_sent_at: null,
    last_error_code: null,
    last_error_at: null,
    created_at: '2026-11-16T08:00:00Z',
    subscribe_link: 'ntfy://ntfy.example.org/lia_AbCdEfGhIjKlMnOpQrStUvWxYz12?display=LIA',
    ...overrides,
  };
}

function overview(overrides: Partial<NtfyOverview> = {}): NtfyOverview {
  return {
    instance_url: 'https://ntfy.example.org',
    custom_servers_enabled: true,
    max_subscriptions: 3,
    subscriptions: [view()],
    ...overrides,
  };
}

const ok = <T,>(data?: T): NtfyActionResult<T> =>
  data === undefined ? { ok: true, errorCode: null } : { ok: true, errorCode: null, data };

function hook(overrides: Partial<Hook> = {}): Hook {
  return {
    overview: overview(),
    firstLoad: false,
    refreshing: false,
    readFailed: false,
    create: vi.fn().mockResolvedValue(ok(view({ id: 'sub-2' }))),
    update: vi.fn().mockResolvedValue(ok(view())),
    remove: vi.fn().mockResolvedValue(ok()),
    test: vi.fn().mockResolvedValue(ok('sent')),
    ...overrides,
  };
}

function offered(on = true): void {
  const config: Pick<AppConfig, 'capabilities'> & { features: Partial<AppConfig['features']> } = {
    features: { ntfy_enabled: true },
    // The operator's switch, as /config publishes it beside the deployment flag.
    capabilities: { ntfy: { enabled: on, family: 'reach' } },
  };
  useAppConfig.mockReturnValue({ config });
}

beforeEach(() => {
  vi.clearAllMocks();
  offered();
  useNtfySubscriptions.mockReturnValue(hook());
  useApplicationAccountQuery.mockReturnValue({
    data: { qr_data_uri: 'data:image/png;base64,AAAA' },
    loading: false,
    error: null,
  });
});

function render() {
  return renderWithProviders(<NtfySettings lng="en" />);
}

describe('NtfySettings', () => {
  it('says nothing and reads nothing while the capability is not offered', () => {
    offered(false);
    useNtfySubscriptions.mockReturnValue(hook({ overview: undefined }));

    const { container } = render();

    expect(container).toBeEmptyDOMElement();
    expect(useNtfySubscriptions).toHaveBeenCalledWith(false);
  });

  it('names each subscription by its server and states its content and its pause', () => {
    useNtfySubscriptions.mockReturnValue(
      hook({
        overview: overview({
          subscriptions: [
            view(),
            view({
              id: 'sub-2',
              server_kind: 'custom',
              server_url: 'https://ntfy.sh',
              content: 'full',
              is_active: false,
            }),
          ],
        }),
      })
    );

    render();

    const rows = screen.getAllByRole('listitem');
    expect(within(rows[0]).getByText(k('server_instance'))).toBeInTheDocument();
    expect(within(rows[0]).getByLabelText(k('content_label'))).toHaveValue('minimal');
    expect(within(rows[0]).queryByText(k('paused'))).not.toBeInTheDocument();
    expect(within(rows[1]).getByText('ntfy.sh')).toBeInTheDocument();
    expect(within(rows[1]).getByLabelText(k('content_label'))).toHaveValue('full');
    expect(within(rows[1]).getByText(k('paused'))).toBeInTheDocument();
  });

  it('says why the last publication failed, in words', () => {
    useNtfySubscriptions.mockReturnValue(
      hook({
        overview: overview({
          subscriptions: [
            view({ last_error_code: 'auth_refused', last_error_at: '2026-11-16T09:00:00Z' }),
          ],
        }),
      })
    );

    render();

    expect(
      screen.getByText(k('last_error', { reason: k('outcome.auth_refused') }))
    ).toBeInTheDocument();
  });

  it('offers only removal for a subscription that can no longer be read', () => {
    useNtfySubscriptions.mockReturnValue(
      hook({ overview: overview({ subscriptions: [view({ topic: null, subscribe_link: null })] }) })
    );

    render();

    expect(screen.getByText(k('unreadable'))).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: k('subscribe') })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: k('test') })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: k('remove') })).toBeInTheDocument();
  });

  it('pauses a subscription with its switch, the switch busy while it saves', async () => {
    let settle: (value: NtfyActionResult<NtfySubscriptionView>) => void = () => {};
    const update = vi.fn(
      () => new Promise<NtfyActionResult<NtfySubscriptionView>>(resolve => (settle = resolve))
    );
    useNtfySubscriptions.mockReturnValue(hook({ update }));
    const { user } = render();

    const toggle = screen.getByRole('switch', { name: k('active_label') });
    await user.click(toggle);

    expect(update).toHaveBeenCalledWith('sub-1', { is_active: false });
    expect(toggle).toHaveAttribute('aria-busy', 'true');
    settle(ok(view({ is_active: false })));
    await waitFor(() => expect(toggle).not.toHaveAttribute('aria-busy'));
  });

  it('changes what the notification shows, the choice held while it saves', async () => {
    let settle: (value: NtfyActionResult<NtfySubscriptionView>) => void = () => {};
    const update = vi.fn(
      () => new Promise<NtfyActionResult<NtfySubscriptionView>>(resolve => (settle = resolve))
    );
    useNtfySubscriptions.mockReturnValue(hook({ update }));
    const { user } = render();
    const select = screen.getByLabelText(k('content_label'));

    await user.selectOptions(select, 'full');

    expect(update).toHaveBeenCalledWith('sub-1', { content: 'full' });
    // The list still says « minimal » until it is read again: the choice does not snap back.
    expect(select).toHaveValue('full');
    expect(select).toHaveAttribute('aria-busy', 'true');
    settle({ ok: false, errorCode: null });
    // Refused: what the server holds is shown again, and the refusal said.
    await waitFor(() => expect(select).toHaveValue('minimal'));
    expect(toast.error).toHaveBeenCalledWith(k('refusal.unknown'));
  });

  it('reports a test the server refused, in words', async () => {
    const test = vi.fn().mockResolvedValue(ok('auth_refused'));
    useNtfySubscriptions.mockReturnValue(hook({ test }));
    const { user } = render();

    await user.click(screen.getByRole('button', { name: k('test') }));

    expect(test).toHaveBeenCalledWith('sub-1');
    expect(toast.error).toHaveBeenCalledWith(
      k('test_failed', { reason: k('outcome.auth_refused') })
    );
  });

  it('removes a subscription only once its removal is confirmed', async () => {
    const remove = vi.fn().mockResolvedValue(ok());
    useNtfySubscriptions.mockReturnValue(hook({ remove }));
    const { user } = render();

    await user.click(screen.getByRole('button', { name: k('remove') }));
    expect(remove).not.toHaveBeenCalled();
    const dialog = await screen.findByRole('alertdialog');
    await user.click(within(dialog).getByRole('button', { name: k('remove') }));

    expect(remove).toHaveBeenCalledWith('sub-1');
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(k('removed')));
  });

  it('subscribes on another server as typed, then shows how to subscribe a device', async () => {
    const created = view({
      id: 'sub-2',
      server_kind: 'custom',
      server_url: 'https://ntfy.sh',
      topic: 'my-alerts',
      subscribe_link: 'ntfy://ntfy.sh/my-alerts?display=LIA',
    });
    const create = vi.fn().mockResolvedValue(ok(created));
    useNtfySubscriptions.mockReturnValue(hook({ create }));
    const { user } = render();

    await user.click(screen.getByRole('button', { name: k('add') }));
    const form = await screen.findByRole('dialog', { name: k('form.title') });
    await user.click(within(form).getByRole('radio', { name: k('form.server_custom') }));
    await user.type(within(form).getByLabelText(k('form.server_url')), 'https://ntfy.sh');
    await user.type(within(form).getByLabelText(k('form.topic')), 'my-alerts');
    await user.click(within(form).getByRole('button', { name: k('form.submit') }));

    expect(create).toHaveBeenCalledWith({
      server: 'custom',
      server_url: 'https://ntfy.sh',
      topic: 'my-alerts',
      content: 'minimal',
    });
    const device = await screen.findByRole('dialog', { name: k('device.title') });
    expect(within(device).getByDisplayValue('my-alerts')).toBeInTheDocument();
    expect(within(device).getByRole('link', { name: k('device.open_app') })).toHaveAttribute(
      'href',
      'ntfy://ntfy.sh/my-alerts?display=LIA'
    );
    expect(within(device).getByRole('img', { name: k('device.qr_alt') })).toBeInTheDocument();
  });

  it('keeps the form open and says why the server refused it', async () => {
    const create = vi.fn().mockResolvedValue({
      ok: false,
      errorCode: 'ntfy_server_url_refused',
    } satisfies NtfyActionResult);
    useNtfySubscriptions.mockReturnValue(hook({ create }));
    const { user } = render();

    await user.click(screen.getByRole('button', { name: k('add') }));
    const form = await screen.findByRole('dialog', { name: k('form.title') });
    await user.click(within(form).getByRole('radio', { name: k('form.server_custom') }));
    await user.type(within(form).getByLabelText(k('form.server_url')), 'https://10.0.0.5');
    await user.click(within(form).getByRole('button', { name: k('form.submit') }));

    expect(await within(form).findByRole('alert')).toHaveTextContent(
      k('refusal.ntfy_server_url_refused', { max: 3 })
    );
    expect(screen.getByRole('dialog', { name: k('form.title') })).toBeInTheDocument();
  });

  it('says the limit instead of offering an add that would be refused', () => {
    useNtfySubscriptions.mockReturnValue(
      hook({
        overview: overview({
          max_subscriptions: 1,
          subscriptions: [view()],
        }),
      })
    );

    render();

    expect(screen.getByText(k('limit_reached', { max: 1 }))).toBeInTheDocument();
    expect(screen.getByRole('button', { name: k('add') })).toHaveAttribute('aria-disabled', 'true');
  });

  it('says the instance offers nothing when there is no server to subscribe on', () => {
    useNtfySubscriptions.mockReturnValue(
      hook({
        overview: overview({
          instance_url: null,
          custom_servers_enabled: false,
          subscriptions: [],
        }),
      })
    );

    render();

    expect(screen.getByText(k('nothing_offered'))).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: k('add') })).not.toBeInTheDocument();
  });
});
