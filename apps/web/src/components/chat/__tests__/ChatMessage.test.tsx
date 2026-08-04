/**
 * ChatMessage — the three bubble shapes (system, assistant, user) and the
 * affordances grafted onto them: copy-to-clipboard, the proactive-interest
 * feedback row, the cost/token line gated by the user preference, the
 * attachment lightbox (opened, dismissed by click, by the close button and by
 * Escape — with the body scroll lock it owns), and the relative timestamp whose
 * four shapes depend on how old the message is.
 *
 * Time-dependent assertions run against a frozen clock and match the *shape*
 * the branch produces rather than re-deriving `Intl` output (which would only
 * restate the implementation).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { makeMessage, makeAttachment, makeUser } from '@/__tests__/factories';
import { usePsycheStore } from '@/stores/psycheStore';
import type { Message } from '@/types/chat';

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));

const { mutate, apiMutationOptions } = vi.hoisted(() => ({
  mutate: vi.fn(async () => {}),
  apiMutationOptions: vi.fn(),
}));
vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: (options: unknown) => {
    apiMutationOptions(options);
    return { mutate };
  },
}));

const { toast } = vi.hoisted(() => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));
vi.mock('sonner', () => ({ toast }));

import { ChatMessage, proactiveFeedbackProps, type ChatMessageProps } from '../ChatMessage';

function renderMessage(message: Message, isUser = false) {
  return renderWithProviders(<ChatMessage message={message} isUser={isUser} />);
}

function renderAssistantWith(message: Message, props: Partial<ChatMessageProps> = {}) {
  return renderWithProviders(<ChatMessage message={message} isUser={false} {...props} />);
}

beforeEach(() => {
  vi.clearAllMocks();
  usePsycheStore.getState().reset();
  useAuth.mockReturnValue({ user: makeUser({ tokens_display_enabled: false }) });
});

describe('ChatMessage — system notice', () => {
  it('renders the notice without the assistant affordances', () => {
    renderMessage(makeMessage({ role: 'system', content: 'Session expired' }));
    expect(screen.getByText('Session expired')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'chat.message.copy' })).not.toBeInTheDocument();
  });
});

describe('ChatMessage — copy to clipboard', () => {
  // `userEvent.setup()` installs its own `navigator.clipboard` stub at render
  // time, so the spy has to be attached AFTER the component is rendered.
  const spyOnClipboard = () => vi.spyOn(navigator.clipboard, 'writeText');

  it('copies the raw message content and confirms', async () => {
    const { user } = renderMessage(makeMessage({ content: 'The answer is 42' }));
    const writeText = spyOnClipboard().mockResolvedValue(undefined);
    await user.click(screen.getByRole('button', { name: 'chat.message.copy' }));
    expect(writeText).toHaveBeenCalledWith('The answer is 42');
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('chat.message.copied'));
  });

  it('reports a clipboard that refuses (permission, insecure context)', async () => {
    const { user } = renderMessage(makeMessage());
    spyOnClipboard().mockRejectedValue(new Error('denied'));
    await user.click(screen.getByRole('button', { name: 'chat.message.copy' }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('chat.message.error'));
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('is not offered on the bubble the user wrote', () => {
    renderMessage(makeMessage({ role: 'user' }), true);
    expect(screen.queryByRole('button', { name: 'chat.message.copy' })).not.toBeInTheDocument();
  });
});

describe('ChatMessage — share/export menu (UX P4)', () => {
  it('offers the actions menu next to Copy on assistant bubbles', () => {
    renderMessage(makeMessage({ content: 'Réponse à partager' }));
    const copy = screen.getByRole('button', { name: 'chat.message.copy' });
    const menu = screen.getByRole('button', { name: 'chat.message.more_actions' });
    expect(copy.closest('div')!.contains(menu)).toBe(true);
  });

  it('is not offered on the bubble the user wrote', () => {
    renderMessage(makeMessage({ role: 'user' }), true);
    expect(screen.queryByRole('button', { name: 'chat.message.more_actions' })).toBeNull();
  });

  it('is not offered on a system notice', () => {
    renderMessage(makeMessage({ role: 'system', content: 'Session expired' }));
    expect(screen.queryByRole('button', { name: 'chat.message.more_actions' })).toBeNull();
  });

  it('is not offered when the bubble has no text to share (image-only answer)', () => {
    renderMessage(makeMessage({ content: '   ' }));
    expect(screen.queryByRole('button', { name: 'chat.message.more_actions' })).toBeNull();
  });
});

describe('ChatMessage — assistant badges', () => {
  it('names the skill that produced the answer', () => {
    renderMessage(makeMessage({ skillName: 'weather-report' }));
    expect(screen.getByText(/weather-report/)).toBeInTheDocument();
  });

  it('marks an answer that was interrupted mid-stream', () => {
    renderMessage(makeMessage({ metadata: { interrupted: true } }));
    expect(screen.getByText(/chat\.message\.interrupted/)).toBeInTheDocument();
  });

  it('says nothing about interruption on a complete answer', () => {
    renderMessage(makeMessage());
    expect(screen.queryByText(/chat\.message\.interrupted/)).not.toBeInTheDocument();
  });

  it('opens a lightbox on a generated image', async () => {
    const { user } = renderMessage(
      makeMessage({ generatedImages: [{ url: 'https://img/1.png', alt: 'a cat' }] })
    );
    await user.click(screen.getByRole('button', { name: 'common.expand_image' }));
    // The enlarged copy joins the thumbnail rather than replacing it.
    expect(await screen.findAllByAltText('a cat')).toHaveLength(2);
  });
});

describe('ChatMessage — cost and token line', () => {
  const billed = makeMessage({
    tokensIn: 12,
    tokensOut: 34,
    tokensCache: 5,
    costEur: 0.0123,
  });

  it('stays hidden while the user has not opted into token display', () => {
    renderMessage(billed);
    expect(screen.queryByText(/GOOGLE/)).not.toBeInTheDocument();
  });

  it('breaks the usage down once token display is on', () => {
    useAuth.mockReturnValue({ user: makeUser({ tokens_display_enabled: true }) });
    renderMessage(billed);
    expect(screen.getByText(/12 IN/)).toBeInTheDocument();
    expect(screen.getByText(/34 OUT/)).toBeInTheDocument();
    expect(screen.getByText(/5 CACHE/)).toBeInTheDocument();
    expect(screen.getByText(/0 GOOGLE/)).toBeInTheDocument();
  });

  it('adds the synthesised-characters badge only for a paid TTS answer', () => {
    useAuth.mockReturnValue({ user: makeUser({ tokens_display_enabled: true }) });
    renderMessage(makeMessage({ ...billed, ttsCharacters: 240, ttsProvider: 'elevenlabs' }));
    expect(screen.getByText(/240 chat\.message\.tts_unit_chars/)).toBeInTheDocument();
  });

  it('omits the badge when the answer was synthesised by the free provider', () => {
    useAuth.mockReturnValue({ user: makeUser({ tokens_display_enabled: true }) });
    renderMessage(makeMessage({ ...billed, ttsCharacters: null }));
    expect(screen.queryByText(/tts_unit_chars/)).not.toBeInTheDocument();
  });

  it('prefers the proactive metadata over the message-level counters', () => {
    useAuth.mockReturnValue({ user: makeUser({ tokens_display_enabled: true }) });
    renderMessage(
      makeMessage({
        tokensIn: 12,
        metadata: { type: 'proactive_heartbeat', tokens_in: 99, tokens_out: 7 },
      })
    );
    expect(screen.getByText(/99 IN/)).toBeInTheDocument();
    expect(screen.queryByText(/12 IN/)).not.toBeInTheDocument();
  });
});

describe('ChatMessage — proactive interest feedback', () => {
  const proactive = (over: Record<string, unknown> = {}) =>
    makeMessage({
      content: 'Un article sur les fusées',
      metadata: {
        type: 'proactive_interest',
        target_id: '11111111-1111-4111-8111-111111111111',
        feedback_enabled: true,
        ...over,
      },
    });

  it('offers the three verdicts on a fresh notification', () => {
    renderMessage(proactive());
    expect(screen.getByRole('button', { name: 'interests.feedback.like' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'interests.feedback.dislike' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'interests.feedback.block' })).toBeInTheDocument();
  });

  it('shows a recorded verdict pressed and disabled, like a voted answer', () => {
    renderMessage(proactive({ feedback_submitted: true, feedback_value: 'thumbs_down' }));

    const down = screen.getByRole('button', { name: 'interests.feedback.dislike' });
    const up = screen.getByRole('button', { name: 'interests.feedback.like' });
    expect(down).toHaveAttribute('aria-pressed', 'true');
    expect(up).toHaveAttribute('aria-pressed', 'false');
    // Final server-side: no chip may re-open the vote.
    expect(down).toBeDisabled();
    expect(up).toBeDisabled();
    expect(screen.getByRole('button', { name: 'interests.feedback.block' })).toBeDisabled();
  });

  it('hides them when the notification does not accept feedback', () => {
    renderMessage(proactive({ feedback_enabled: false }));
    expect(
      screen.queryByRole('button', { name: 'interests.feedback.like' })
    ).not.toBeInTheDocument();
  });

  it.each([
    ['interests.feedback.like', 'thumbs_up'],
    ['interests.feedback.dislike', 'thumbs_down'],
    ['interests.feedback.block', 'block'],
  ])('posts %s as the recorded verdict', async (label, verdict) => {
    const { user } = renderMessage(proactive());
    await user.click(screen.getByRole('button', { name: label }));
    await waitFor(() =>
      expect(mutate).toHaveBeenCalledWith(
        '/interests/11111111-1111-4111-8111-111111111111/feedback',
        { feedback: verdict }
      )
    );
  });

  it('acknowledges the verdict and accepts no second vote', async () => {
    const { user } = renderMessage(proactive());
    const like = screen.getByRole('button', { name: 'interests.feedback.like' });

    await user.click(like);

    expect(toast.success).toHaveBeenCalledWith('interests.feedback.liked');
    await waitFor(() => expect(like).toBeDisabled());
    // A second click on any chip must not reach the endpoint.
    await user.click(screen.getByRole('button', { name: 'interests.feedback.block' }));
    expect(mutate).toHaveBeenCalledTimes(1);
  });

  it('uses the neutral wording for the negative verdicts', async () => {
    const { user } = renderMessage(proactive());
    await user.click(screen.getByRole('button', { name: 'interests.feedback.block' }));
    expect(toast.info).toHaveBeenCalledWith('interests.feedback.blocked');
  });
});

describe('ChatMessage — proactive interest feedback, audit trail', () => {
  it('carries the notification run_id so the verdict lands on the right row', async () => {
    // The audit column stayed NULL on 989 production rows because nothing tied
    // a verdict to a notification. The card knows its run_id — it must send it.
    const { user } = renderMessage(
      makeMessage({
        content: 'Un article sur les fusées',
        metadata: {
          type: 'proactive_interest',
          target_id: '11111111-1111-4111-8111-111111111111',
          run_id: 'interest_11111111_ab12cd34',
          feedback_enabled: true,
        },
      })
    );

    await user.click(screen.getByRole('button', { name: 'interests.feedback.like' }));

    await waitFor(() =>
      expect(mutate).toHaveBeenCalledWith(
        '/interests/11111111-1111-4111-8111-111111111111/feedback',
        {
          feedback: 'thumbs_up',
          run_id: 'interest_11111111_ab12cd34',
        }
      )
    );
  });
});

describe('ChatMessage — proactive heartbeat feedback', () => {
  // 914 heartbeat notifications carried `feedback_enabled: true` and had a
  // working endpoint, but no component ever rendered buttons for them.
  const heartbeat = (over: Record<string, unknown> = {}) =>
    makeMessage({
      content: 'Il pleuvra cet après-midi',
      metadata: {
        type: 'proactive_heartbeat',
        target_id: '22222222-2222-4222-8222-222222222222',
        feedback_enabled: true,
        ...over,
      },
    });

  it('offers the two verdicts its contract accepts', () => {
    renderMessage(heartbeat());
    expect(screen.getByRole('button', { name: 'heartbeat.feedback.like' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'heartbeat.feedback.dislike' })).toBeInTheDocument();
  });

  it('puts the verdicts in the action row next to Copy, not under the text', () => {
    // The same gesture must look the same everywhere: an ordinary answer shows
    // its thumbs as chips of the action row, and a proactive notification used
    // to show them inside the bubble, introduced by a full sentence.
    renderMessage(heartbeat());

    const copy = screen.getByRole('button', { name: 'chat.message.copy' });
    const like = screen.getByRole('button', { name: 'heartbeat.feedback.like' });
    const row = copy.closest('div');

    expect(row, 'the copy chip must sit in a row').not.toBeNull();
    expect(row!.contains(like), 'the thumbs belong to the copy chip row').toBe(true);
  });

  it('introduces the verdicts with no sentence of its own', () => {
    renderMessage(heartbeat());
    // The former "Was this notification useful?" line, now removed with its key.
    expect(screen.queryByText(/heartbeat\.feedback\.helpful/)).not.toBeInTheDocument();
  });

  it('treats an INTEREST notification exactly the same way', () => {
    // Homogeneity is the point: the two kinds of proactive push must not look
    // like two features. Same slot (the copy chip's row), same absence of an
    // introductory sentence — only the set of verdicts differs.
    renderMessage(
      makeMessage({
        content: 'Un article sur les fusées',
        metadata: {
          type: 'proactive_interest',
          target_id: '11111111-1111-4111-8111-111111111111',
          feedback_enabled: true,
        },
      })
    );

    const copy = screen.getByRole('button', { name: 'chat.message.copy' });
    const like = screen.getByRole('button', { name: 'interests.feedback.like' });
    expect(copy.closest('div')!.contains(like)).toBe(true);
    expect(screen.queryByText(/interests\.notification\.helpful/)).not.toBeInTheDocument();
    // The interest contract keeps its third verdict.
    expect(screen.getByRole('button', { name: 'interests.feedback.block' })).toBeInTheDocument();
  });

  it('never offers "block" — the heartbeat contract has no such verdict', () => {
    renderMessage(heartbeat());
    expect(
      screen.queryByRole('button', { name: 'interests.feedback.block' })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'heartbeat.feedback.block' })
    ).not.toBeInTheDocument();
  });

  it('patches the heartbeat notification endpoint, not the interest one', async () => {
    const { user } = renderMessage(heartbeat());

    await user.click(screen.getByRole('button', { name: 'heartbeat.feedback.like' }));

    await waitFor(() =>
      expect(mutate).toHaveBeenCalledWith(
        '/heartbeat/notifications/22222222-2222-4222-8222-222222222222/feedback',
        {
          feedback: 'thumbs_up',
        }
      )
    );
    expect(apiMutationOptions).toHaveBeenCalledWith(expect.objectContaining({ method: 'PATCH' }));
  });

  it('acknowledges the verdict and locks the row on THAT verdict', async () => {
    const { user } = renderMessage(heartbeat());

    await user.click(screen.getByRole('button', { name: 'heartbeat.feedback.dislike' }));

    expect(toast.info).toHaveBeenCalledWith('heartbeat.feedback.disliked');
    // The chosen thumb — not another one — is the one shown as pressed.
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'heartbeat.feedback.dislike' })).toHaveAttribute(
        'aria-pressed',
        'true'
      )
    );
    expect(screen.getByRole('button', { name: 'heartbeat.feedback.like' })).toHaveAttribute(
      'aria-pressed',
      'false'
    );
    expect(screen.getByRole('button', { name: 'heartbeat.feedback.dislike' })).toBeDisabled();
    expect(mutate).toHaveBeenCalledTimes(1);
  });

  it('shows a recorded verdict pressed and disabled', () => {
    renderMessage(heartbeat({ feedback_submitted: true, feedback_value: 'thumbs_up' }));

    const up = screen.getByRole('button', { name: 'heartbeat.feedback.like' });
    expect(up).toHaveAttribute('aria-pressed', 'true');
    expect(up).toBeDisabled();
    expect(screen.getByRole('button', { name: 'heartbeat.feedback.dislike' })).toBeDisabled();
  });

  it('stays hidden when the notification does not accept feedback', () => {
    renderMessage(heartbeat({ feedback_enabled: false }));
    expect(
      screen.queryByRole('button', { name: 'heartbeat.feedback.like' })
    ).not.toBeInTheDocument();
  });
});

describe('proactiveFeedbackProps — which contract a bubble routes to', () => {
  // Both backend routes declare their path parameter as a UUID
  // (`POST /interests/{interest_id}/feedback`,
  // `PATCH /heartbeat/notifications/{notification_id}/feedback`), so the
  // identifier a card carries has to be one.
  const TARGET = '3f4a1c8e-9d2b-4e7a-8c15-6b0d2f9a7e31';
  const base = { target_id: TARGET, feedback_enabled: true };

  it.each([
    ['proactive_interest', 'interest'],
    ['proactive_heartbeat', 'heartbeat'],
  ])('routes %s to the %s contract', (type, kind) => {
    expect(proactiveFeedbackProps({ ...base, type })).toEqual({
      kind,
      targetId: TARGET,
      runId: undefined,
      submittedVerdict: undefined,
    });
  });

  it('keeps the run_id when the card carries one', () => {
    expect(proactiveFeedbackProps({ ...base, type: 'proactive_interest', run_id: 'r-9' })).toEqual({
      kind: 'interest',
      targetId: TARGET,
      runId: 'r-9',
      submittedVerdict: undefined,
    });
  });

  it.each([
    ['an ordinary assistant message', {}],
    ['an unknown proactive kind', { ...base, type: 'proactive_phone_call' }],
    ['a card without a target', { type: 'proactive_interest', feedback_enabled: true }],
    ['an empty target', { ...base, type: 'proactive_interest', target_id: '' }],
    [
      'a card that refuses feedback',
      { ...base, type: 'proactive_interest', feedback_enabled: false },
    ],
  ])('offers nothing for %s', (_label, metadata) => {
    expect(proactiveFeedbackProps(metadata as Record<string, unknown>)).toBeNull();
  });

  // Heartbeat notifications archived BEFORE the identity fix carry a
  // synthetic `heartbeat_<hex>` target. The route would reject it with a 422
  // that the buttons deliberately swallow, so the user would press a control
  // that silently records nothing. Offering no control at all is the honest
  // reading: the vote is genuinely impossible on those rows.
  it.each([
    ['a legacy heartbeat identifier', 'heartbeat_ab12cd34', 'proactive_heartbeat'],
    ['a non-uuid interest identifier', 'x-1', 'proactive_interest'],
    [
      'a uuid-shaped but invalid target',
      '3f4a1c8e-9d2b-4e7a-8c15-6b0d2f9a7e3',
      'proactive_interest',
    ],
  ])('offers nothing for %s', (_label, targetId, type) => {
    expect(
      proactiveFeedbackProps({ feedback_enabled: true, target_id: targetId, type })
    ).toBeNull();
  });

  it('reports the verdict of this session over the persisted one', () => {
    // Right after a click the metadata is still the pre-vote payload.
    expect(
      proactiveFeedbackProps(
        { ...base, type: 'proactive_interest', feedback_value: 'thumbs_up' },
        'block'
      )
    ).toMatchObject({ submittedVerdict: 'block' });
  });

  it('reads the persisted verdict when this session has not voted', () => {
    expect(
      proactiveFeedbackProps({ ...base, type: 'proactive_interest', feedback_value: 'thumbs_down' })
    ).toMatchObject({ submittedVerdict: 'thumbs_down' });
  });

  it('ignores a verdict value it does not know', () => {
    expect(
      proactiveFeedbackProps({ ...base, type: 'proactive_interest', feedback_value: 'shrug' })
    ).toMatchObject({ submittedVerdict: undefined });
  });

  it('offers nothing without metadata at all', () => {
    expect(proactiveFeedbackProps(undefined)).toBeNull();
  });

  it('ignores a non-string run_id instead of forwarding garbage', () => {
    expect(proactiveFeedbackProps({ ...base, type: 'proactive_interest', run_id: 42 })).toEqual({
      kind: 'interest',
      targetId: TARGET,
      runId: undefined,
      submittedVerdict: undefined,
    });
  });
});

describe('ChatMessage — bubble action row (PERSO)', () => {
  // The Copy / 👍 / 👎 controls live in ONE in-flow row at the bubble's bottom
  // (interest-notification pattern) — never an overlay covering the text.

  it('hides the whole action row while the answer is still streaming', () => {
    renderAssistantWith(makeMessage(), { isActiveStream: true, streamPhase: 'answer' });
    expect(screen.queryByRole('button', { name: 'chat.message.copy' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'chat.feedback.up' })).not.toBeInTheDocument();
  });

  it('lays copy and the feedback chips side by side, in flow, on an archived answer', () => {
    renderAssistantWith(makeMessage({ metadata: { message_db_id: 'db-1' } }));
    const copy = screen.getByRole('button', { name: 'chat.message.copy' });
    const up = screen.getByRole('button', { name: 'chat.feedback.up' });
    expect(screen.getByRole('button', { name: 'chat.feedback.down' })).toBeInTheDocument();
    // In flow — no overlay positioning on any of the controls.
    expect(copy.className).not.toMatch(/absolute/);
    expect(up.className).not.toMatch(/absolute/);
    // One shared flex row, copy first in document order.
    expect(up.parentElement).toBe(copy.parentElement);
    expect(copy.compareDocumentPosition(up) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('renders copy alone when the answer has no archived DB id', () => {
    renderAssistantWith(makeMessage());
    expect(screen.getByRole('button', { name: 'chat.message.copy' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'chat.feedback.up' })).not.toBeInTheDocument();
  });

  it('keeps the interest verdicts and adds the copy row on proactive notifications', () => {
    renderAssistantWith(
      makeMessage({
        metadata: {
          type: 'proactive_interest',
          target_id: '33333333-3333-4333-8333-333333333333',
          feedback_enabled: true,
          message_db_id: 'db-9',
        },
      })
    );
    expect(screen.getByRole('button', { name: 'interests.feedback.like' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'chat.message.copy' })).toBeInTheDocument();
    // Response-feedback chips never appear on proactive rows (dedicated verdicts).
    expect(screen.queryByRole('button', { name: 'chat.feedback.up' })).not.toBeInTheDocument();
  });
});

describe('ChatMessage — user bubble', () => {
  it('shows the account picture when there is one', () => {
    renderMessage(makeMessage({ role: 'user', avatar: 'https://cdn/me.png' }), true);
    expect(screen.getByAltText('chat.avatar_alt.user')).toBeInTheDocument();
  });

  it('falls back to the generic icon without a picture', () => {
    renderMessage(makeMessage({ role: 'user' }), true);
    expect(screen.queryByAltText('chat.avatar_alt.user')).not.toBeInTheDocument();
  });

  it('reports the transcription length of a voice message', () => {
    renderMessage(
      makeMessage({ role: 'user', source: 'voice', sttAudioDurationSeconds: 3.2 }),
      true
    );
    expect(screen.getByText(/🎤 3\.2/)).toBeInTheDocument();
  });

  it('adds the remote-STT cost only when token display is on', () => {
    useAuth.mockReturnValue({ user: makeUser({ tokens_display_enabled: true }) });
    renderMessage(
      makeMessage({
        role: 'user',
        source: 'voice',
        sttAudioDurationSeconds: 3,
        sttCostEur: 0.0004,
        sttProvider: 'elevenlabs',
      }),
      true
    );
    expect(screen.getByTitle(/stt_tooltip_provider/)).toBeInTheDocument();
  });

  it('keeps a typed message free of any voice indicator', () => {
    renderMessage(makeMessage({ role: 'user', source: 'text' }), true);
    expect(screen.queryByText(/stt_unit_seconds/)).not.toBeInTheDocument();
  });
});

describe('ChatMessage — attachment lightbox', () => {
  const withImage = () =>
    makeMessage({
      role: 'user',
      metadata: { attachments: [makeAttachment({ filename: 'facture.png' })] },
    });

  async function open(user: ReturnType<typeof renderMessage>['user']) {
    await user.click(screen.getByRole('button', { name: 'facture.png' }));
    return screen.findByRole('dialog', { name: 'facture.png' });
  }

  it('links a document attachment instead of previewing it', () => {
    renderMessage(
      makeMessage({
        role: 'user',
        metadata: {
          attachments: [
            makeAttachment({
              id: 'att-9',
              filename: 'contrat.pdf',
              mime_type: 'application/pdf',
              content_type: 'document',
            }),
          ],
        },
      }),
      true
    );
    const link = screen.getByRole('link', { name: 'contrat.pdf' });
    expect(link).toHaveAttribute('href', expect.stringContaining('att-9'));
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('opens the image in a modal dialog and locks the page scroll', async () => {
    const { user } = renderMessage(withImage(), true);
    expect(document.body.style.overflow).not.toBe('hidden');

    const dialog = await open(user);
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(document.body.style.overflow).toBe('hidden');
  });

  it('closes on Escape and gives the page its scroll back', async () => {
    const { user } = renderMessage(withImage(), true);
    await open(user);

    await user.keyboard('{Escape}');

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(document.body.style.overflow).not.toBe('hidden');
  });

  it('closes on the close button', async () => {
    const { user } = renderMessage(withImage(), true);
    await open(user);
    await user.click(screen.getByRole('button', { name: 'common.close' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('stays open when the image itself is clicked', async () => {
    const { user } = renderMessage(withImage(), true);
    const dialog = await open(user);
    await user.click(screen.getAllByAltText('facture.png')[1]);
    expect(dialog).toBeInTheDocument();
  });

  it('renders nothing when the message carries no attachment', () => {
    renderMessage(makeMessage({ role: 'user', metadata: { attachments: [] } }), true);
    expect(screen.queryByRole('button', { name: /\.png$/ })).not.toBeInTheDocument();
  });
});

describe('ChatMessage — relative timestamp', () => {
  const NOW = new Date('2026-07-19T14:30:00');
  const DAY_MS = 86_400_000;

  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(NOW);
  });
  afterEach(() => vi.useRealTimers());

  const daysAgo = (n: number) => new Date(NOW.getTime() - n * DAY_MS);

  it('shows only the time for today', () => {
    renderMessage(makeMessage({ timestamp: daysAgo(0) }));
    expect(screen.getByText(/^\d{2}:\d{2}$/)).toBeInTheDocument();
  });

  it('labels yesterday', () => {
    renderMessage(makeMessage({ timestamp: daysAgo(1) }));
    expect(screen.getByText(/^chat\.date\.yesterday \d{2}:\d{2}$/)).toBeInTheDocument();
  });

  it('names the weekday within the last week', () => {
    renderMessage(makeMessage({ timestamp: daysAgo(3) }));
    const stamp = screen.getByText(/\d{2}:\d{2}$/);
    expect(stamp.textContent).not.toMatch(/chat\.date\.yesterday/);
    // Weekday + time, and the capitalisation the branch applies.
    expect(stamp.textContent).toMatch(/^\p{Lu}\p{L}+ \d{2}:\d{2}$/u);
  });

  it('falls back to the full date beyond a week', () => {
    renderMessage(makeMessage({ timestamp: daysAgo(30) }));
    expect(screen.getByText(/^\d{2}:\d{2} \| .+/)).toBeInTheDocument();
  });
});

describe('ChatMessage — peer bubble (peers Lot 7)', () => {
  const peerMessage = () =>
    makeMessage({
      content: 'Marie te fait dire bonjour',
      metadata: {
        type: 'proactive_peer_message',
        target_id: 'm1',
        sender_id: 'p1',
        sender_name: 'Marie Dupont',
      },
    });

  it('tints the bubble and offers the quick actions on a relayed message', () => {
    renderAssistantWith(peerMessage(), { onPrefillComposer: vi.fn() });
    const bubble = screen.getByText('Marie te fait dire bonjour').closest('.message-bubble');
    expect(bubble).toHaveClass('bg-primary/10');
    // A peer type also matches the generic `proactive_` prefix: the peer tint
    // must win, never the red proactive one.
    expect(bubble).not.toHaveClass('bg-destructive/10');
    expect(screen.getByRole('button', { name: /chat\.peer\.reply/ })).toBeInTheDocument();
  });

  it('wires the composer prefill through the actions row', async () => {
    const onPrefillComposer = vi.fn();
    const { user } = renderAssistantWith(peerMessage(), { onPrefillComposer });
    await user.click(screen.getByRole('button', { name: /chat\.peer\.reply/ }));
    expect(onPrefillComposer).toHaveBeenCalledWith('chat.peer.reply_prefill');
    expect(mutate).not.toHaveBeenCalled();
  });

  it('keeps the default surface and no peer actions on a plain answer', () => {
    renderMessage(makeMessage({ content: 'Réponse ordinaire' }));
    const bubble = screen.getByText('Réponse ordinaire').closest('.message-bubble');
    expect(bubble).not.toHaveClass('bg-primary/10');
    expect(bubble).not.toHaveClass('bg-destructive/10');
    expect(screen.queryByRole('button', { name: /chat\.peer\.reply/ })).toBeNull();
  });
});

describe('ChatMessage — proactive bubble tint (owner request 2026-08-05)', () => {
  it('tints a proactive notification light red so it reads apart from answers', () => {
    renderMessage(
      makeMessage({
        content: 'Un article sur les fusées',
        metadata: { type: 'proactive_interest', target_id: '11111111-1111-4111-8111-111111111111' },
      })
    );
    const bubble = screen.getByText('Un article sur les fusées').closest('.message-bubble');
    expect(bubble).toHaveClass('bg-destructive/10');
    expect(bubble).not.toHaveClass('bg-primary/10');
  });

  it('tints every proactive family the same way (heartbeat)', () => {
    renderMessage(
      makeMessage({ content: 'Votre journée commence', metadata: { type: 'proactive_heartbeat' } })
    );
    const bubble = screen.getByText('Votre journée commence').closest('.message-bubble');
    expect(bubble).toHaveClass('bg-destructive/10');
  });

  it('keeps the error bubble on the default glass — red is the proactive code here', () => {
    renderMessage(makeMessage({ content: 'Une erreur est survenue', metadata: { type: 'error' } }));
    const bubble = screen.getByText('Une erreur est survenue').closest('.message-bubble');
    expect(bubble).not.toHaveClass('bg-destructive/10');
    expect(bubble).toHaveClass('bg-card/70');
  });
});
