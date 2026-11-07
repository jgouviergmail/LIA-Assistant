/**
 * A form filled from one sentence (ADR-372, lot 4): the form is the review, so the answer goes
 * straight to it and the dialog closes; a refusal keeps the person's words; what it cost stays in
 * sight, nothing was saved.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { ApiError } from '@/lib/api-client';
import type { AssistAnswer } from '@/lib/workbench/assist';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { post },
}));

import { SentenceAssist } from '../SentenceAssist';

interface Filled extends AssistAnswer {
  summary: string;
}

const ANSWER: Filled = {
  summary: 'Lunch',
  usage: { tokens_in: 90, tokens_out: 30, tokens_cache: 0, cost_eur: 0.001, model_name: 'm' },
};

function draw() {
  const onAnswer = vi.fn();
  const rendered = renderWithProviders(
    <SentenceAssist<Filled>
      lng="en"
      label="Describe it"
      path="/tool-assists/calendar/from-words"
      maxInstruction={100}
      onAnswer={onAnswer}
    />
  );
  return { ...rendered, onAnswer };
}

async function say(user: ReturnType<typeof draw>['user'], words: string) {
  await user.click(screen.getByRole('button', { name: 'Describe it' }));
  await user.type(await screen.findByRole('textbox'), words);
  await user.click(screen.getByRole('button', { name: 'workbench.assist.writing.ask' }));
}

beforeEach(() => {
  post.mockReset();
  post.mockResolvedValue(ANSWER);
});

describe('SentenceAssist', () => {
  it('asks nothing until the person has said something', async () => {
    const { user } = draw();

    await user.click(screen.getByRole('button', { name: 'Describe it' }));
    await user.click(await screen.findByRole('button', { name: 'workbench.assist.writing.ask' }));

    expect(post).not.toHaveBeenCalled();
  });

  it('hands the answer to the form and closes: the form is the review', async () => {
    const { user, onAnswer } = draw();

    await say(user, 'Lunch Thursday at noon');

    await waitFor(() => expect(onAnswer).toHaveBeenCalledWith(ANSWER));
    expect(post.mock.calls[0][1]).toEqual({ sentence: 'Lunch Thursday at noon' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('keeps what it cost in sight once the form is filled', async () => {
    const { user } = draw();

    await say(user, 'Lunch Thursday at noon');

    expect(await screen.findByText(/common\.llm_usage\.tokens/)).toBeInTheDocument();
  });

  it('tells a refusal and keeps the person’s words', async () => {
    post.mockRejectedValueOnce(new ApiError('no', 422, { detail: { code: 'assist_not_found' } }));
    const { user, onAnswer } = draw();

    await say(user, 'Nothing to plan');

    expect(await screen.findByRole('alert')).toHaveTextContent('workbench.errors.assist_not_found');
    expect(screen.getByRole('textbox')).toHaveValue('Nothing to plan');
    expect(onAnswer).not.toHaveBeenCalled();
  });

  it('leaves without touching the form', async () => {
    let signal: AbortSignal | undefined;
    post.mockImplementationOnce((_path: string, _body: unknown, config: RequestInit) => {
      signal = config.signal ?? undefined;
      return new Promise(() => undefined);
    });
    const { user, onAnswer } = draw();

    await say(user, 'Lunch');
    await user.click(await screen.findByRole('button', { name: 'common.cancel' }));

    expect(signal?.aborted).toBe(true);
    expect(onAnswer).not.toHaveBeenCalled();
  });
});
