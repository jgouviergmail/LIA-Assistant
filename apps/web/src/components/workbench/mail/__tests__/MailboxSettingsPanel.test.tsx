/**
 * Gmail's mailbox settings (ADR-369, Tasks 4.6-4.7), through the real hook:
 * the vacation responder saved as a whole in the account's own days, the
 * filters listed as what they match and what they do, and created once per
 * submission — a refusal keeps the form AND its key, so trying again is the
 * same submission, never a second filter.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  act,
  answerConfirmDialog,
  fireEvent,
  renderWithProviders,
  screen,
  waitFor,
} from '@/__tests__/test-utils';
import { ApiError } from '@/lib/api-client';
import type { MailFilter, MailVacation, WorkbenchFeature } from '@/lib/workbench/types';

const { api, i18n } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  // One stable `t` that shows the quoted value, so a filter's summary is read.
  i18n: {
    t: (key: string, values?: { value?: string }) =>
      values?.value ? `${key}:${values.value}` : key,
    i18n: { language: 'en' },
  },
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'owner' } }) }));
vi.mock('@/i18n/client', () => ({ useTranslation: () => i18n }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: api,
}));
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), error: vi.fn(), warn: vi.fn(), info: vi.fn() },
}));

import { MailboxSettingsPanel } from '../MailboxSettingsPanel';

const VACATION = '/workbench/mail/vacation';
const FILTERS = '/workbench/mail/filters';

const AWAY: MailVacation = {
  enabled: true,
  subject: 'Away',
  body: 'Back on Monday.',
  start_date: '2026-11-02',
  end_date: '2026-11-06',
};

function filter(overrides: Partial<MailFilter> = {}): MailFilter {
  return {
    id: 'f1',
    sender: null,
    recipient: null,
    subject: null,
    query: null,
    has_attachment: false,
    add_label_ids: [],
    archive: false,
    mark_read: false,
    forward: null,
    name: null,
    read_only: false,
    ...overrides,
  };
}

let vacation: MailVacation;
let filters: MailFilter[];

beforeEach(() => {
  vi.clearAllMocks();
  vacation = { ...AWAY };
  filters = [];
  api.get.mockImplementation((path: string) =>
    Promise.resolve(path === VACATION ? vacation : { filters })
  );
  api.put.mockImplementation((_path: string, body: MailVacation) => Promise.resolve(body));
  api.post.mockResolvedValue(filter({ id: 'created' }));
});

const GMAIL: WorkbenchFeature[] = [
  'vacation',
  'vacation_subject',
  'vacation_open_end',
  'filters',
  'filter_words',
  'labels',
];
const OUTLOOK: WorkbenchFeature[] = ['vacation', 'filters'];

function panel({
  open = true,
  features = GMAIL,
  signature = '',
  onSaveSignature = vi.fn().mockResolvedValue(undefined),
}: {
  open?: boolean;
  features?: WorkbenchFeature[];
  signature?: string;
  onSaveSignature?: (text: string) => Promise<void>;
} = {}) {
  const onSaved = vi.fn();
  const onRefused = vi.fn();
  const rendered = renderWithProviders(
    <MailboxSettingsPanel
      lng="en"
      open={open}
      onOpenChange={vi.fn()}
      tool={{
        tool: 'mail',
        state: 'ready',
        provider: 'google_gmail',
        features,
        bounds: { search_max_chars: 200, signature_max_chars: 1000 },
      }}
      labels={[{ id: 'Label_7', kind: 'user', role: null, name: 'Work' }]}
      signature={signature}
      onSaveSignature={onSaveSignature}
      onRefused={onRefused}
      onSaved={onSaved}
    />
  );
  return { ...rendered, onSaved, onRefused, onSaveSignature };
}

function readsOf(path: string): number {
  return api.get.mock.calls.filter(([called]) => called === path).length;
}

describe('MailboxSettingsPanel — on Outlook', () => {
  it('asks no subject: an automatic reply has none', async () => {
    panel({ features: OUTLOOK });

    await screen.findByLabelText('workbench.mail.settings.vacation_text');
    expect(screen.queryByLabelText('workbench.mail.compose.subject')).toBeNull();
  });

  it('sends none either', async () => {
    const { user } = panel({ features: OUTLOOK });

    await user.click(await screen.findByRole('button', { name: 'workbench.mail.settings.save' }));

    await waitFor(() => expect(api.put).toHaveBeenCalled());
    expect(api.put.mock.calls[0]?.[1]).not.toHaveProperty('subject');
  });

  it('asks a last day for a first one, sending nothing until then', async () => {
    vacation = { ...AWAY, end_date: null };
    const { user } = panel({ features: OUTLOOK });

    await user.click(await screen.findByRole('button', { name: 'workbench.mail.settings.save' }));

    expect(await screen.findByText('workbench.mail.settings.last_day_needed')).toBeVisible();
    expect(api.put).not.toHaveBeenCalled();
  });

  it('keeps Gmail free of it', async () => {
    vacation = { ...AWAY, end_date: null };
    const { user } = panel();

    await user.click(await screen.findByRole('button', { name: 'workbench.mail.settings.save' }));

    await waitFor(() => expect(api.put).toHaveBeenCalled());
  });

  it("says a connection must be renewed, in the refusal's words", async () => {
    api.get.mockImplementation(() =>
      Promise.reject(new ApiError('refused', 409, { detail: { code: 'reconnect_required' } }))
    );
    panel({ features: OUTLOOK });

    expect(await screen.findByText('workbench.errors.reconnect_required')).toBeInTheDocument();
  });

  it('offers no words: no rule reads a Gmail search', async () => {
    const { user } = panel({ features: OUTLOOK });

    await filtersTab(user);

    await screen.findByLabelText('workbench.mail.filters.sender');
    expect(screen.queryByLabelText('workbench.mail.filters.words')).toBeNull();
  });

  it('moves to a folder, where Gmail applies a label', async () => {
    filters = [filter({ sender: 'a@example.org', add_label_ids: ['Label_7'] })];
    const { user } = panel({ features: OUTLOOK });

    await filtersTab(user);

    expect(await screen.findByLabelText('workbench.mail.filters.move_to')).toBeInTheDocument();
    expect(await screen.findByText(/workbench.mail.filters.moves_to/)).toBeInTheDocument();
    expect(screen.queryByLabelText('workbench.mail.filters.add_label')).toBeNull();
  });

  it('offers no deletion of a rule only Outlook can change', async () => {
    filters = [filter({ sender: 'a@example.org', read_only: true })];
    const { user } = panel({ features: OUTLOOK });

    await filtersTab(user);

    await screen.findByText(/workbench.mail.filters.from_is/);
    expect(screen.queryByRole('button', { name: 'workbench.mail.filters.row_actions' })).toBeNull();
  });

  it('names a rule whose conditions no field here reads', async () => {
    filters = [filter({ name: 'Old rule', mark_read: true })];
    const { user } = panel({ features: OUTLOOK });

    await filtersTab(user);

    expect(await screen.findByText('workbench.mail.filters.named:Old rule')).toBeInTheDocument();
  });
});

async function filtersTab(user: ReturnType<typeof panel>['user']) {
  await user.click(screen.getByRole('tab', { name: 'workbench.mail.settings.filters' }));
}

describe('MailboxSettingsPanel — the signature', () => {
  const text = () => screen.getByLabelText('workbench.mail.settings.signature_label');

  it('is offered on a mailbox with no setting of its own', () => {
    panel({ features: [], signature: 'Ana' });

    expect(text()).toHaveValue('Ana');
    expect(screen.queryByRole('tab', { name: 'workbench.mail.settings.vacation' })).toBeNull();
  });

  it('keeps what is written, and says so', async () => {
    const { user, onSaveSignature, onSaved } = panel({ features: [], signature: '' });

    await user.type(text(), 'Ana');
    await user.click(screen.getByRole('button', { name: 'workbench.mail.settings.save' }));

    await waitFor(() =>
      expect(onSaved).toHaveBeenCalledWith('workbench.mail.settings.signature_saved')
    );
    expect(onSaveSignature).toHaveBeenCalledWith('Ana');
  });

  it('says a refusal and keeps what was typed', async () => {
    const refused = new Error('no');
    const { user, onRefused, onSaved } = panel({
      features: [],
      signature: '',
      onSaveSignature: vi.fn().mockRejectedValue(refused),
    });

    await user.type(text(), 'Ana');
    await user.click(screen.getByRole('button', { name: 'workbench.mail.settings.save' }));

    await waitFor(() => expect(onRefused).toHaveBeenCalledWith(refused));
    expect(onSaved).not.toHaveBeenCalled();
    expect(text()).toHaveValue('Ana');
  });

  it('draws the bound the server keeps', () => {
    panel({ features: [], signature: '' });

    expect(text()).toHaveAttribute('maxlength', '1000');
  });
});

describe('MailboxSettingsPanel — the vacation responder', () => {
  it('reads nothing while closed, and only what the provider offers once open', async () => {
    const closed = panel({ open: false });
    // The first read leaves on a microtask: give it every chance before judging.
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    expect(api.get).not.toHaveBeenCalled();
    closed.unmount();

    panel({ features: ['vacation', 'vacation_subject'] });
    await screen.findByDisplayValue('Away');
    expect(readsOf(FILTERS)).toBe(0);
    expect(screen.queryByRole('tab', { name: 'workbench.mail.settings.filters' })).toBeNull();
  });

  it('saves the responder as a whole, in the account’s days, and says so', async () => {
    const { user, onSaved } = panel();
    const subject = await screen.findByDisplayValue('Away');

    await user.type(subject, ' — on leave');
    await user.click(screen.getByRole('button', { name: 'workbench.mail.settings.save' }));

    await waitFor(() =>
      expect(onSaved).toHaveBeenCalledWith('workbench.mail.settings.vacation_saved')
    );
    // Path and body: the mutation's own plumbing is not the contract.
    expect(api.put.mock.calls[0].slice(0, 2)).toEqual([
      VACATION,
      {
        enabled: true,
        subject: 'Away — on leave',
        body: 'Back on Monday.',
        start_date: '2026-11-02',
        end_date: '2026-11-06',
      },
    ]);
    // The form is rebuilt from what was saved, never from the first read.
    await user.click(screen.getByRole('tab', { name: 'workbench.mail.settings.filters' }));
    await user.click(screen.getByRole('tab', { name: 'workbench.mail.settings.vacation' }));
    expect(await screen.findByDisplayValue('Away — on leave')).toBeInTheDocument();
  });

  it('turns the responder off with nothing else, and an empty day is no day', async () => {
    const { user } = panel();
    const first = await screen.findByLabelText('workbench.mail.settings.first_day');

    fireEvent.change(first, { target: { value: '' } });
    await user.click(screen.getByRole('button', { name: 'workbench.mail.settings.save' }));
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1));
    expect(api.put.mock.calls[0][1]).toMatchObject({ start_date: null, end_date: '2026-11-06' });

    await user.click(screen.getByRole('switch'));
    expect(screen.queryByLabelText('workbench.mail.settings.first_day')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'workbench.mail.settings.save' }));
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(2));
    expect(api.put.mock.calls[1][1]).toEqual({ enabled: false });
  });

  it('refuses a period that ends before it starts, sending nothing', async () => {
    const { user } = panel();
    const last = await screen.findByLabelText('workbench.mail.settings.last_day');

    fireEvent.change(last, { target: { value: '2026-11-01' } });
    expect(screen.getByText('workbench.mail.period.reversed')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'workbench.mail.settings.save' }));
    // Also where the browser's own `min` check would let the form through.
    fireEvent.submit(last.closest('form') as HTMLFormElement);

    expect(api.put).not.toHaveBeenCalled();
  });

  it('says a refusal and keeps what was typed', async () => {
    const refusal = new ApiError('refused', 502, { detail: { code: 'provider_unavailable' } });
    api.put.mockRejectedValueOnce(refusal);
    const { user, onSaved, onRefused } = panel();
    const subject = await screen.findByDisplayValue('Away');

    await user.clear(subject);
    await user.type(subject, 'Gone fishing');
    await user.click(screen.getByRole('button', { name: 'workbench.mail.settings.save' }));

    await waitFor(() => expect(onRefused).toHaveBeenCalledWith(refusal));
    expect(onSaved).not.toHaveBeenCalled();
    expect(screen.getByDisplayValue('Gone fishing')).toBeInTheDocument();
  });

  it('says so when the responder could not be read', async () => {
    api.get.mockImplementation((path: string) =>
      path === VACATION ? Promise.reject(new ApiError('down', 502)) : Promise.resolve({ filters })
    );
    panel();

    expect(await screen.findByText('workbench.mail.settings.failed')).toBeInTheDocument();
  });
});

describe('MailboxSettingsPanel — the filters', () => {
  it('lists each filter as what it matches and what it does', async () => {
    filters = [
      filter({
        sender: 'ana@example.org',
        subject: 'Invoice',
        has_attachment: true,
        add_label_ids: ['Label_7', 'Label_gone'],
        archive: true,
        mark_read: true,
        forward: 'me@example.org',
      }),
    ];
    const { user } = panel();
    await filtersTab(user);

    expect(
      await screen.findByText(
        'workbench.mail.filters.from_is:ana@example.org · workbench.mail.filters.subject_has:Invoice · workbench.mail.filters.has_attachment'
      )
    ).toBeInTheDocument();
    // A label the account no longer lists is named by its id, never dropped.
    expect(
      screen.getByText(
        'workbench.mail.filters.labels_as:Work · workbench.mail.filters.labels_as:Label_gone · workbench.mail.filters.archives · workbench.mail.filters.marks_read · workbench.mail.filters.forwards_to:me@example.org'
      )
    ).toBeInTheDocument();
  });

  describe('deleting one', () => {
    const DELETE = /^workbench\.mail\.filters\.delete/;

    async function asked(accept: boolean) {
      filters = [filter({ id: 'f9', sender: 'ana@example.org', archive: true })];
      const rendered = panel();
      await filtersTab(rendered.user);
      await rendered.user.click(await screen.findByRole('button', { name: DELETE }));
      await answerConfirmDialog(rendered.user, accept);
      return rendered;
    }

    it('asks first, then deletes it and reads the list again', async () => {
      filters = [filter({ id: 'f9', sender: 'ana@example.org', archive: true })];
      const { onSaved } = await asked(true);

      await waitFor(() =>
        expect(api.delete).toHaveBeenCalledWith(FILTERS, { params: { filter_id: 'f9' } })
      );
      await waitFor(() => expect(readsOf(FILTERS)).toBe(2));
      expect(onSaved).toHaveBeenCalledWith('workbench.mail.settings.filter_deleted');
    });

    it('says what the filter matches and does before anything goes', async () => {
      filters = [filter({ id: 'f9', sender: 'ana@example.org', archive: true })];
      const { user } = panel();
      await filtersTab(user);

      await user.click(await screen.findByRole('button', { name: DELETE }));

      const question = await screen.findByRole('alertdialog');
      expect(question).toHaveTextContent('workbench.mail.filters.from_is:ana@example.org');
      expect(question).toHaveTextContent('workbench.mail.filters.archives');
      expect(question).toHaveTextContent('workbench.mail.filters.delete_description');
    });

    it('tells two filters apart for the ear', async () => {
      filters = [
        filter({ id: 'f1', sender: 'ana@example.org', archive: true }),
        filter({ id: 'f2', sender: 'bea@example.org', archive: true }),
      ];
      const { user } = panel();
      await filtersTab(user);

      expect(
        await screen.findByRole('button', { name: /delete:.*ana@example\.org/ })
      ).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /delete:.*bea@example\.org/ })).toBeInTheDocument();
    });

    it('deletes nothing when the answer is no', async () => {
      const { onSaved } = await asked(false);

      expect(api.delete).not.toHaveBeenCalled();
      expect(onSaved).not.toHaveBeenCalled();
    });

    it('takes a filter already gone for a deletion done', async () => {
      api.delete.mockRejectedValueOnce(
        new ApiError('gone', 404, { detail: { code: 'item_gone' } })
      );
      const { onSaved, onRefused } = await asked(true);

      await waitFor(() => expect(onSaved).toHaveBeenCalled());
      expect(onRefused).not.toHaveBeenCalled();
    });

    it('says a refusal, and reads nothing more', async () => {
      const refusal = new ApiError('down', 503, { detail: { code: 'provider_unavailable' } });
      api.delete.mockRejectedValueOnce(refusal);
      const { onSaved, onRefused } = await asked(true);

      await waitFor(() => expect(onRefused).toHaveBeenCalledWith(refusal));
      expect(onSaved).not.toHaveBeenCalled();
      expect(readsOf(FILTERS)).toBe(1);
    });
  });

  it('says when there is none, and when the list could not be read', async () => {
    const empty = panel();
    await filtersTab(empty.user);
    expect(await screen.findByText('workbench.mail.filters.none')).toBeInTheDocument();
    empty.unmount();

    api.get.mockImplementation((path: string) =>
      path === FILTERS ? Promise.reject(new ApiError('down', 502)) : Promise.resolve(vacation)
    );
    const failed = panel();
    await filtersTab(failed.user);
    expect(await screen.findByText('workbench.mail.settings.failed')).toBeInTheDocument();
  });

  it('sends nothing until the filter matches something and does something', async () => {
    const { user } = panel();
    await filtersTab(user);
    const create = await screen.findByRole('button', { name: 'workbench.mail.filters.create' });

    await user.click(create);
    expect(screen.getByRole('alert')).toHaveTextContent('workbench.mail.filters.needs_matches');
    await user.type(screen.getByLabelText('workbench.mail.filters.sender'), '   ');
    await user.click(create);
    expect(screen.getByRole('alert')).toHaveTextContent('workbench.mail.filters.needs_matches');

    await user.type(screen.getByLabelText('workbench.mail.filters.sender'), 'ana@example.org');
    await user.click(create);
    expect(screen.getByRole('alert')).toHaveTextContent('workbench.mail.filters.needs_acts');
    expect(api.post).not.toHaveBeenCalled();
  });

  it('creates once per submission, trimmed, then starts over and re-reads the list', async () => {
    const { user, onSaved } = panel();
    await filtersTab(user);
    await screen.findByText('workbench.mail.filters.none');
    const sender = screen.getByLabelText('workbench.mail.filters.sender');

    await user.type(sender, '  ana@example.org  ');
    await user.selectOptions(screen.getByLabelText('workbench.mail.filters.add_label'), 'Label_7');
    await user.click(screen.getByLabelText('workbench.mail.filters.archive'));
    const readsBefore = readsOf(FILTERS);
    await user.click(screen.getByRole('button', { name: 'workbench.mail.filters.create' }));

    await waitFor(() =>
      expect(onSaved).toHaveBeenCalledWith('workbench.mail.settings.filter_created')
    );
    const [path, first] = api.post.mock.calls[0];
    expect(path).toBe(FILTERS);
    expect(first).toEqual({
      sender: 'ana@example.org',
      add_label_id: 'Label_7',
      archive: true,
      idempotency_key: expect.any(String),
    });
    expect(readsOf(FILTERS)).toBe(readsBefore + 1);
    expect(sender).toHaveValue('');
    expect(screen.getByLabelText('workbench.mail.filters.archive')).not.toBeChecked();

    await user.type(sender, 'bob@example.org');
    await user.click(screen.getByLabelText('workbench.mail.filters.mark_read'));
    await user.click(screen.getByRole('button', { name: 'workbench.mail.filters.create' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
    expect(api.post.mock.calls[1][1].idempotency_key).not.toBe(first.idempotency_key);
  });

  it('keeps the form and its key after a refusal, so trying again is the same submission', async () => {
    const refusal = new ApiError('refused', 502, { detail: { code: 'provider_unavailable' } });
    api.post.mockRejectedValueOnce(refusal);
    const { user, onRefused, onSaved } = panel();
    await filtersTab(user);
    await screen.findByText('workbench.mail.filters.none');

    await user.type(screen.getByLabelText('workbench.mail.filters.words'), 'newsletter');
    await user.click(screen.getByLabelText('workbench.mail.filters.mark_read'));
    await user.click(screen.getByRole('button', { name: 'workbench.mail.filters.create' }));
    await waitFor(() => expect(onRefused).toHaveBeenCalledWith(refusal));
    expect(screen.getByLabelText('workbench.mail.filters.words')).toHaveValue('newsletter');

    await user.click(screen.getByRole('button', { name: 'workbench.mail.filters.create' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(api.post.mock.calls[1][1].idempotency_key).toBe(
      api.post.mock.calls[0][1].idempotency_key
    );
  });

  it('creates nothing more on a second press, and a list that cannot be re-read is no refusal', async () => {
    let finish: (created: MailFilter) => void = () => undefined;
    api.post.mockImplementationOnce(() => new Promise<MailFilter>(resolve => (finish = resolve)));
    const { user, onSaved, onRefused } = panel();
    await filtersTab(user);
    await screen.findByText('workbench.mail.filters.none');
    await user.type(screen.getByLabelText('workbench.mail.filters.subject'), 'Invoice');
    await user.click(screen.getByLabelText('workbench.mail.filters.archive'));
    const create = screen.getByRole('button', { name: 'workbench.mail.filters.create' });

    await user.click(create);
    fireEvent.submit(create.closest('form') as HTMLFormElement);
    api.get.mockImplementation((path: string) =>
      path === FILTERS ? Promise.reject(new ApiError('down', 502)) : Promise.resolve(vacation)
    );
    finish(filter({ id: 'created' }));

    await waitFor(() =>
      expect(onSaved).toHaveBeenCalledWith('workbench.mail.settings.filter_created')
    );
    expect(api.post).toHaveBeenCalledTimes(1);
    expect(onRefused).not.toHaveBeenCalled();
  });
});
