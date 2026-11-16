/**
 * WritingStyleSettings — what LIA learned of how the person writes, learned at their
 * click (ADR-383, amendment 2026-11-16).
 *
 * The real hook chain runs (account query, mutations); only the HTTP client is
 * replaced. Proven: the first load, the learned profile shown as TEXT, the switch
 * saved and its state answered, a failed save said, learning at a click — one request
 * however many clicks, the button keeping its focus while it works, what was learned
 * read back, the outcome said with what it cost — each outcome and refusal said in
 * its own words, « Forget » held while a learning runs, forgetting behind a
 * confirmation with the focus handed back to the switch, and a failed read retried.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { makeUser } from '@/__tests__/factories';
import { act, renderWithProviders, screen, userEvent, waitFor } from '@/__tests__/test-utils';
import { ApiError } from '@/lib/api-client';
import { publishApplicationResources } from '@/lib/application-resources';
import type { LLMUsage } from '@/types/llm-usage';
import type { WritingStyle, WritingStyleLearning } from '@/types/writing-style';

const { get, patch, post, del } = vi.hoisted(() => ({
  get: vi.fn(),
  patch: vi.fn(),
  post: vi.fn(),
  del: vi.fn(),
}));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: { ...original.default, get, patch, post, delete: del } };
});
const auth = vi.hoisted((): { user: ReturnType<typeof makeUser> | null } => ({ user: null }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: auth.user }) }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { learningNotice, WritingStyleSettings, writingStyleState } from '../WritingStyleSettings';

const PREFIX = 'settings.writing_style';
const PROFILE = 'Writes « Salut », signs <b>Seb</b>.';
const NOTHING = { profile: null, mails_read: null, learned_at: null };
const COST: LLMUsage = {
  tokens_in: 900,
  tokens_out: 60,
  tokens_cache: 0,
  cost_eur: 0.002,
  model_name: 'm',
};

function style(over: Partial<WritingStyle> = {}): WritingStyle {
  return {
    enabled: true,
    mails_to_read: 30,
    profile: PROFILE,
    mails_read: 12,
    learned_at: '2026-11-13T09:00:00Z',
    ...over,
  };
}

function answer(over: Partial<WritingStyleLearning> = {}): WritingStyleLearning {
  return { outcome: 'learned', mails_read: 12, usage: COST, ...over };
}

function refused(code: string, status = 403): ApiError {
  return new ApiError('refused', status, { detail: { code } });
}

/** A request the test answers when it chooses. */
function deferred<T>() {
  let resolve: (value: T) => void = () => undefined;
  const promise = new Promise<T>(settle => {
    resolve = settle;
  });
  return { promise, resolve };
}

function render() {
  return renderWithProviders(<WritingStyleSettings lng="en" />);
}

async function theSwitch() {
  return screen.findByRole('switch', { name: `${PREFIX}.enable` });
}

function status() {
  return screen.getByRole('status');
}

beforeEach(() => {
  vi.clearAllMocks();
  auth.user = makeUser({ id: 'writer', timezone: 'Europe/Paris' });
  get.mockResolvedValue(style());
});

describe('writingStyleState', () => {
  it('says what was learned, too little, nothing yet, or nothing while off', () => {
    expect(writingStyleState(style())).toBe('learned');
    expect(writingStyleState(style({ profile: null, mails_read: 2 }))).toBe('too_few');
    expect(writingStyleState(style(NOTHING))).toBe('nothing_yet');
    expect(writingStyleState(style({ ...NOTHING, enabled: false }))).toBe('off_nothing');
  });
});

describe('learningNotice', () => {
  it.each([
    ['learned', 'default', false],
    ['too_few', 'default', false],
    ['no_mailbox', 'warning', true],
    ['reconnect', 'warning', true],
    ['switched_off', 'default', false],
    ['superseded', 'default', false],
  ] as const)('says the %s outcome in its own sentence', (outcome, tone, toConnectors) => {
    const notice = learningNotice({ answered: true, learning: answer({ outcome }) });

    expect(notice).toEqual({
      tone,
      toConnectors,
      key: `${PREFIX}.outcome.${outcome}`,
      usage: COST,
    });
  });

  it('says a mailbox refusing LIA while it is read as the reconnect outcome', () => {
    const notice = learningNotice({ answered: false, error: refused('reconnect_required') });

    expect(notice).toEqual({
      tone: 'warning',
      toConnectors: true,
      key: `${PREFIX}.outcome.reconnect`,
      usage: null,
    });
  });

  it('says a refusal in the workbench words, with the wait it names', () => {
    expect(learningNotice({ answered: false, error: refused('assist_quota') })).toMatchObject({
      tone: 'error',
      key: 'workbench.errors.assist_quota',
      toConnectors: false,
      usage: null,
    });
    const throttled = new ApiError('slow down', 429, { detail: { retry_after_seconds: 30 } });
    expect(learningNotice({ answered: false, error: throttled })).toMatchObject({
      key: 'workbench.errors.provider_rate_limited_wait',
      values: { seconds: 30 },
    });
  });

  it('says anything else as the generic error', () => {
    expect(learningNotice({ answered: false, error: new Error('down') })).toMatchObject({
      tone: 'error',
      key: 'common.error',
    });
  });
});

describe('WritingStyleSettings', () => {
  it('shows the learned profile as text, with its switch on', async () => {
    render();

    expect(await theSwitch()).toHaveAttribute('aria-checked', 'true');
    expect(get).toHaveBeenCalledWith('/writing-style', expect.anything());
    // Model output is text, never markup.
    expect(screen.getByText(PROFILE)).toBeInTheDocument();
    expect(screen.getByText(`${PREFIX}.learned_meta`)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: `${PREFIX}.learn_again` })).toBeInTheDocument();
  });

  it('learns at a click, once, keeping the focus, and shows what it learned and its cost', async () => {
    get.mockResolvedValueOnce(style(NOTHING)).mockResolvedValue(style());
    const pending = deferred<WritingStyleLearning>();
    post.mockReturnValue(pending.promise);
    render();
    const button = await screen.findByRole('button', { name: `${PREFIX}.learn` });
    expect(screen.getByText(`${PREFIX}.nothing_yet`)).toBeInTheDocument();

    await userEvent.click(button);
    await userEvent.click(button);

    expect(post).toHaveBeenCalledTimes(1);
    expect(post).toHaveBeenCalledWith('/writing-style/learn', undefined, undefined);
    expect(button).toHaveAttribute('aria-busy', 'true');
    expect(button).toHaveFocus();
    pending.resolve(answer());

    expect(await screen.findByText(PROFILE)).toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(2);
    expect(status()).toHaveTextContent(`${PREFIX}.outcome.learned`);
    expect(status()).toHaveTextContent(`${PREFIX}.learning_cost`);
    // The same control, renamed in place: the focus never left it.
    const again = screen.getByRole('button', { name: `${PREFIX}.learn_again` });
    expect(again).toBe(button);
    expect(again).toHaveFocus();
    expect(again).not.toHaveAttribute('aria-busy');
  });

  it('leads to the connectors when no mailbox can be read, and spends nothing', async () => {
    get.mockResolvedValue(style(NOTHING));
    post.mockResolvedValue(answer({ outcome: 'no_mailbox', mails_read: 0, usage: null }));
    render();

    await userEvent.click(await screen.findByRole('button', { name: `${PREFIX}.learn` }));

    await waitFor(() => expect(status()).toHaveTextContent(`${PREFIX}.outcome.no_mailbox`));
    expect(
      screen.getByRole('link', { name: `${PREFIX}.open_connectors` }).getAttribute('href')
    ).toBe('/en/dashboard/settings?section=connectors');
    expect(status()).not.toHaveTextContent(`${PREFIX}.learning_cost`);
  });

  it('says a refusal in its own words and keeps what was learned', async () => {
    post.mockRejectedValue(refused('assist_quota'));
    render();

    await userEvent.click(await screen.findByRole('button', { name: `${PREFIX}.learn_again` }));

    await waitFor(() => expect(status()).toHaveTextContent('workbench.errors.assist_quota'));
    expect(screen.getByText(PROFILE)).toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(1);
  });

  it('hands the focus to the switch when the switch went off meanwhile', async () => {
    get.mockResolvedValueOnce(style(NOTHING)).mockResolvedValue(style({ ...NOTHING, enabled: false }));
    post.mockResolvedValue(answer({ outcome: 'switched_off', mails_read: 0, usage: null }));
    render();
    const control = await theSwitch();

    await userEvent.click(screen.getByRole('button', { name: `${PREFIX}.learn` }));

    await waitFor(() => expect(status()).toHaveTextContent(`${PREFIX}.outcome.switched_off`));
    expect(screen.queryByRole('button', { name: `${PREFIX}.learn` })).not.toBeInTheDocument();
    await waitFor(() => expect(control).toHaveFocus());
  });

  it('says a style forgotten or learned again meanwhile, its cost, and what stands now', async () => {
    get.mockResolvedValueOnce(style()).mockResolvedValue(style(NOTHING));
    post.mockResolvedValue(answer({ outcome: 'superseded' }));
    render();
    const button = await screen.findByRole('button', { name: `${PREFIX}.learn_again` });

    await userEvent.click(button);

    await waitFor(() => expect(status()).toHaveTextContent(`${PREFIX}.outcome.superseded`));
    // What was spent is said even when nothing was kept.
    expect(status()).toHaveTextContent(`${PREFIX}.learning_cost`);
    // What stands is read back: the forgetting, not the learning that ended after it.
    expect(await screen.findByText(`${PREFIX}.nothing_yet`)).toBeInTheDocument();
    expect(screen.queryByText(PROFILE)).not.toBeInTheDocument();
    const learn = screen.getByRole('button', { name: `${PREFIX}.learn` });
    expect(learn).toBe(button);
    expect(learn).toHaveFocus();
  });

  it('holds « Forget » while a learning runs: the learning would be paid for nothing', async () => {
    const pending = deferred<WritingStyleLearning>();
    post.mockReturnValue(pending.promise);
    render();
    await userEvent.click(await screen.findByRole('button', { name: `${PREFIX}.learn_again` }));
    const forgetButton = screen.getByRole('button', { name: `${PREFIX}.forget` });

    expect(forgetButton).toHaveAttribute('aria-disabled', 'true');
    await userEvent.click(forgetButton);

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    pending.resolve(answer());
    await waitFor(() => expect(forgetButton).not.toHaveAttribute('aria-disabled'));
  });

  it('tells the next account nothing of a learning that ends after a switch of account', async () => {
    const pending = deferred<WritingStyleLearning>();
    post.mockReturnValue(pending.promise);
    const { rerender } = render();
    await userEvent.click(await screen.findByRole('button', { name: `${PREFIX}.learn_again` }));

    auth.user = makeUser({ id: 'someone-else', timezone: 'Europe/Paris' });
    get.mockResolvedValue(style({ profile: 'Writes like someone else.' }));
    rerender(<WritingStyleSettings lng="en" />);
    const theirs = await screen.findByRole('button', { name: `${PREFIX}.learn_again` });
    // The first account's act does not run in the second one's page.
    expect(theirs).not.toHaveAttribute('aria-busy');
    pending.resolve(answer());

    await waitFor(() => expect(screen.getByText('Writes like someone else.')).toBeInTheDocument());
    await new Promise(settle => setTimeout(settle, 0));
    expect(status()).toBeEmptyDOMElement();
    // Its answer read nothing back either: two reads, one per account.
    expect(get).toHaveBeenCalledTimes(2);
  });

  it.each(['writing_style', 'profile'] as const)(
    'reads the style again when the assistant changed it from a conversation (%s)',
    async resource => {
      render();
      await screen.findByText(PROFILE);
      get.mockResolvedValue(style({ profile: 'Learned again from the chat.' }));

      act(() => publishApplicationResources('someone-else', new Set([resource])));
      expect(get).toHaveBeenCalledTimes(1);
      act(() => publishApplicationResources('writer', new Set([resource])));

      expect(await screen.findByText('Learned again from the chat.')).toBeInTheDocument();
      expect(get).toHaveBeenCalledTimes(2);
    }
  );

  it('offers no learning while switched off, and keeps what was learned forgettable', async () => {
    get.mockResolvedValue(style({ enabled: false }));
    render();

    expect(await screen.findByText(`${PREFIX}.off_kept`)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: `${PREFIX}.learn_again` })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: `${PREFIX}.forget` })).toBeInTheDocument();
  });

  it('saves the switch and shows the state the server answers', async () => {
    patch.mockResolvedValue(style({ enabled: false }));
    render();
    const control = await theSwitch();

    await userEvent.click(control);

    await waitFor(() => expect(control).toHaveAttribute('aria-checked', 'false'));
    expect(patch).toHaveBeenCalledWith('/writing-style', { writing_style_enabled: false }, undefined);
    expect(screen.getByText(`${PREFIX}.off_kept`)).toBeInTheDocument();
    expect(toast.success).toHaveBeenCalledWith(`${PREFIX}.switched_off`);
    expect(control).toHaveFocus();
  });

  it('says a failed save and keeps what is shown', async () => {
    patch.mockRejectedValue(new Error('down'));
    render();
    const control = await theSwitch();

    await userEvent.click(control);

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('common.error'));
    expect(control).toHaveAttribute('aria-checked', 'true');
  });

  it('forgets only after confirming, and hands the focus back to the switch', async () => {
    del.mockResolvedValue(undefined);
    render();
    const control = await theSwitch();

    await userEvent.click(screen.getByRole('button', { name: `${PREFIX}.forget` }));
    expect(del).not.toHaveBeenCalled();
    const dialog = await screen.findByRole('alertdialog');
    await userEvent.click(
      Array.from(dialog.querySelectorAll('button')).find(
        button => button.textContent === `${PREFIX}.forget`
      )!
    );

    await waitFor(() => expect(del).toHaveBeenCalledWith('/writing-style', expect.anything()));
    await waitFor(() => expect(screen.getByText(`${PREFIX}.nothing_yet`)).toBeInTheDocument());
    expect(screen.queryByText(PROFILE)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: `${PREFIX}.forget` })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: `${PREFIX}.learn` })).toBeInTheDocument();
    await waitFor(() => expect(control).toHaveFocus());
    expect(toast.success).toHaveBeenCalledWith(`${PREFIX}.forgotten`);
  });

  it('says too few sent e-mails, with what was read still forgettable', async () => {
    get.mockResolvedValue(style({ profile: null, mails_read: 2 }));
    render();

    expect(await screen.findByText(`${PREFIX}.too_few`)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: `${PREFIX}.forget` })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: `${PREFIX}.learn_again` })).toBeInTheDocument();
  });

  it('offers to retry a failed read, and retries it', async () => {
    get.mockRejectedValueOnce(new Error('down'));
    render();

    await userEvent.click(await screen.findByRole('button', { name: 'common.retry' }));

    expect(await theSwitch()).toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(2);
  });
});
