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

const { mutate } = vi.hoisted(() => ({ mutate: vi.fn(async () => {}) }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation: () => ({ mutate }) }));

const { toast } = vi.hoisted(() => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));
vi.mock('sonner', () => ({ toast }));

import { ChatMessage, type ChatMessageProps } from '../ChatMessage';

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
        target_id: 'int-7',
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

  it('hides them again once a verdict was already recorded server-side', () => {
    renderMessage(proactive({ feedback_submitted: true }));
    expect(
      screen.queryByRole('button', { name: 'interests.feedback.like' })
    ).not.toBeInTheDocument();
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
      expect(mutate).toHaveBeenCalledWith('/interests/int-7/feedback', { feedback: verdict })
    );
  });

  it('acknowledges the verdict and closes the row for good (no double vote)', async () => {
    const { user } = renderMessage(proactive());
    await user.click(screen.getByRole('button', { name: 'interests.feedback.like' }));
    expect(toast.success).toHaveBeenCalledWith('interests.feedback.liked');
    await waitFor(() =>
      expect(
        screen.queryByRole('button', { name: 'interests.feedback.like' })
      ).not.toBeInTheDocument()
    );
    expect(mutate).toHaveBeenCalledTimes(1);
  });

  it('uses the neutral wording for the negative verdicts', async () => {
    const { user } = renderMessage(proactive());
    await user.click(screen.getByRole('button', { name: 'interests.feedback.block' }));
    expect(toast.info).toHaveBeenCalledWith('interests.feedback.blocked');
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
          target_id: 'int-1',
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
