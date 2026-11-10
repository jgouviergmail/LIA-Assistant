/**
 * Writing with LIA (ADR-372): one icon beside a field, a list under it, and a proposal the person
 * reads before anything changes. Words already written are never replaced without being asked, and
 * leaving costs what was spent and changes nothing.
 */
import { MessageSquareReply, PenLine } from '@/lib/icons';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { ApiError } from '@/lib/api-client';

const { post, hearing } = vi.hoisted(() => ({ post: vi.fn(), hearing: { dictates: false } }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { post },
}));
vi.mock('../../WorkbenchShell', () => ({
  useAssistBounds: () => ({ textMax: 100, instructionMax: 100, dictates: hearing.dictates }),
}));

vi.mock('@/components/selection-assist/DictationAct', () => ({
  DictationAct: ({ onWords, onEnd }: { onWords: (words: string) => void; onEnd: () => void }) => (
    <button
      type="button"
      onClick={() => {
        onWords('Said aloud');
        onEnd();
      }}
    >
      listening
    </button>
  ),
}));

import { WritingAssist, type WritingLine } from '../WritingAssist';

const OPEN = 'workbench.assist.writing.open';
const REPLACE = 'workbench.assist.writing.replace';
const ADD = 'workbench.assist.writing.add';
const USE = 'workbench.assist.writing.use';
const ASK = 'workbench.assist.writing.ask';
const WORDS = { text: 'Dear Ana, yes.', usage: null };

const SHORTEN: WritingLine = {
  key: 'shorten',
  label: 'Shorten',
  icon: PenLine,
  path: '/tool-assists/text/rewrite',
  body: () => ({ text: 'Long words', tone: 'shorter' }),
};
const REPLY: WritingLine = {
  key: 'reply',
  label: 'Propose a reply',
  icon: MessageSquareReply,
  path: '/tool-assists/mail/reply',
  body: instruction => ({ message_id: 'm1', instruction }),
  instruction: 'optional',
  suggestions: ['Accept', 'Decline'],
};
const FROM_WORDS: WritingLine = { ...REPLY, key: 'compose', instruction: 'required' };

function draw(overrides: Partial<Parameters<typeof WritingAssist>[0]> = {}) {
  const onApply = vi.fn();
  const rendered = renderWithProviders(
    <WritingAssist
      lng="en"
      lines={[SHORTEN, REPLY]}
      blank={false}
      maxInstruction={100}
      onApply={onApply}
      {...overrides}
    />
  );
  return { ...rendered, onApply };
}

async function pick(user: ReturnType<typeof draw>['user'], label: string) {
  await user.click(screen.getByRole('button', { name: OPEN }));
  await user.click(await screen.findByRole('menuitem', { name: label }));
}

beforeEach(() => {
  post.mockReset();
  post.mockResolvedValue(WORDS);
  hearing.dictates = false;
});

describe('WritingAssist — an instruction said aloud', () => {
  const SAY = 'workbench.assist.voice.dictate';

  it('takes the instruction by voice where words can be said, asking nothing by itself', async () => {
    hearing.dictates = true;
    const { user } = draw({ lines: [FROM_WORDS] });

    await pick(user, 'Propose a reply');
    await user.type(screen.getByRole('textbox'), 'Thank Ana,');
    await user.click(screen.getByRole('button', { name: SAY }));
    await user.click(await screen.findByRole('button', { name: 'listening' }));

    expect(screen.getByRole('textbox')).toHaveValue('Thank Ana, Said aloud');
    expect(await screen.findByRole('button', { name: SAY })).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('offers no microphone where nothing can hear', async () => {
    const { user } = draw({ lines: [FROM_WORDS] });

    await pick(user, 'Propose a reply');

    expect(screen.getByRole('textbox')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: SAY })).toBeNull();
  });

  it('opens a line that needs words on its form, and waits for them', async () => {
    draw({ lines: [FROM_WORDS], startWith: 'compose' });

    expect(await screen.findByRole('textbox')).toHaveValue('');
    await new Promise(resolve => setTimeout(resolve, 10));
    expect(post).not.toHaveBeenCalled();
  });
});

describe('WritingAssist — dictation', () => {
  const DICTATE = 'workbench.assist.voice.dictate';

  it('offers nothing to say where nothing can hear', async () => {
    const { user } = draw();

    await user.click(screen.getByRole('button', { name: OPEN }));

    await screen.findByRole('menuitem', { name: 'Shorten' });
    expect(screen.queryByRole('menuitem', { name: DICTATE })).toBeNull();
  });

  it('stands in the icon’s place while it listens, then gives it back', async () => {
    const onDictated = vi.fn();
    const { user } = draw({ onDictated });

    await pick(user, DICTATE);

    expect(screen.queryByRole('button', { name: OPEN })).toBeNull();
    await user.click(await screen.findByRole('button', { name: 'listening' }));

    expect(onDictated).toHaveBeenCalledWith('Said aloud');
    expect(await screen.findByRole('button', { name: OPEN })).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('is offered alone on a field with nothing else to propose', async () => {
    const { user } = draw({ lines: [], onDictated: vi.fn() });

    await user.click(screen.getByRole('button', { name: OPEN }));

    expect(await screen.findByRole('menuitem', { name: DICTATE })).toBeInTheDocument();
  });
});

describe('WritingAssist', () => {
  it('stands as one icon, its lines under it, and asks nothing until one is pressed', async () => {
    const { user } = draw();

    await user.click(screen.getByRole('button', { name: OPEN }));

    const lines = await screen.findAllByRole('menuitem');
    expect(lines.map(line => line.textContent)).toEqual(['Shorten', 'Propose a reply']);
    expect(post).not.toHaveBeenCalled();
  });

  it('shows the proposal first: nothing changes until the person says so', async () => {
    const { user, onApply } = draw();

    await pick(user, 'Shorten');

    expect(await screen.findByText('Dear Ana, yes.')).toBeInTheDocument();
    expect(post.mock.calls[0][0]).toBe('/tool-assists/text/rewrite');
    expect(post.mock.calls[0][1]).toEqual({ text: 'Long words', tone: 'shorter' });
    expect(onApply).not.toHaveBeenCalled();
  });

  it('offers to replace the person’s words or to add after them', async () => {
    const { user, onApply } = draw();

    await pick(user, 'Shorten');
    await user.click(await screen.findByRole('button', { name: ADD }));

    expect(onApply).toHaveBeenCalledWith(WORDS, 'add', SHORTEN);
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('replaces only when asked to', async () => {
    const { user, onApply } = draw();

    await pick(user, 'Shorten');
    await user.click(await screen.findByRole('button', { name: REPLACE }));

    expect(onApply).toHaveBeenCalledWith(WORDS, 'replace', SHORTEN);
  });

  it('has nothing to replace in an empty field: one word says it', async () => {
    const { user, onApply } = draw({ blank: true });

    await pick(user, 'Shorten');
    await user.click(await screen.findByRole('button', { name: USE }));

    expect(onApply).toHaveBeenCalledWith(WORDS, 'replace', SHORTEN);
    expect(screen.queryByRole('button', { name: ADD })).toBeNull();
  });

  it('takes the person’s instruction before asking', async () => {
    const { user } = draw();

    await pick(user, 'Propose a reply');
    expect(post).not.toHaveBeenCalled();
    await user.type(screen.getByRole('textbox'), 'Say yes');
    await user.click(screen.getByRole('button', { name: ASK }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][1]).toEqual({ message_id: 'm1', instruction: 'Say yes' });
  });

  it('keeps its submit to itself: inside a composer it must never send the message', async () => {
    const onOuterSubmit = vi.fn((event: React.FormEvent) => event.preventDefault());
    const { user } = renderWithProviders(
      <form onSubmit={onOuterSubmit}>
        <WritingAssist
          lng="en"
          lines={[REPLY]}
          blank={false}
          maxInstruction={100}
          onApply={vi.fn()}
        />
      </form>
    );

    await user.click(screen.getByRole('button', { name: OPEN }));
    await user.click(await screen.findByRole('menuitem', { name: 'Propose a reply' }));
    await user.click(screen.getByRole('button', { name: ASK }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(onOuterSubmit).not.toHaveBeenCalled();
  });

  it('asks without one where it is optional', async () => {
    const { user } = draw();

    await pick(user, 'Propose a reply');
    await user.click(screen.getByRole('button', { name: ASK }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][1]).toEqual({ message_id: 'm1', instruction: null });
  });

  it('holds back where the words are needed, and keeps the focus', async () => {
    const { user } = draw({ lines: [FROM_WORDS] });

    await pick(user, 'Propose a reply');
    const ask = screen.getByRole('button', { name: ASK });
    await user.click(ask);

    expect(ask).toHaveAttribute('aria-disabled', 'true');
    expect(post).not.toHaveBeenCalled();
  });

  it('puts a suggestion in the field in one press, and sends nothing by itself', async () => {
    const { user } = draw();

    await pick(user, 'Propose a reply');
    await user.click(screen.getByRole('button', { name: 'Accept' }));

    expect(screen.getByRole('textbox')).toHaveValue('Accept');
    expect(post).not.toHaveBeenCalled();
  });

  it('bounds the instruction as the route does', async () => {
    const { user } = draw();

    await pick(user, 'Propose a reply');

    expect(screen.getByRole('textbox')).toHaveAttribute('maxlength', '100');
  });

  it('opens by itself on the line it was opened for, at once', async () => {
    draw({ startWith: 'reply' });

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][0]).toBe('/tool-assists/mail/reply');
    expect(post.mock.calls[0][1]).toEqual({ message_id: 'm1', instruction: null });
    expect(await screen.findByText('Dear Ana, yes.')).toBeInTheDocument();
  });

  it('tells a refusal, and keeps the instruction for another try', async () => {
    post.mockRejectedValueOnce(new ApiError('no', 502, { detail: { code: 'assist_failed' } }));
    const { user } = draw();

    await pick(user, 'Propose a reply');
    await user.type(screen.getByRole('textbox'), 'Say yes');
    await user.click(screen.getByRole('button', { name: ASK }));

    expect(await screen.findByRole('alert')).toHaveTextContent('workbench.errors.assist_failed');
    expect(screen.getByRole('textbox')).toHaveValue('Say yes');
  });

  it('asks again from the same dialog, what was answered leaving with it', async () => {
    post.mockResolvedValueOnce(WORDS);
    post.mockResolvedValueOnce({ text: 'Dear Ana, no.', usage: null });
    const { user } = draw();

    await pick(user, 'Propose a reply');
    await user.click(screen.getByRole('button', { name: ASK }));
    await screen.findByText('Dear Ana, yes.');
    await user.click(screen.getByRole('button', { name: ASK }));

    expect(await screen.findByText('Dear Ana, no.')).toBeInTheDocument();
    expect(screen.queryByText('Dear Ana, yes.')).toBeNull();
  });

  it('leaves without changing anything, and stops what is on its way', async () => {
    let signal: AbortSignal | undefined;
    post.mockImplementationOnce((_path: string, _body: unknown, config: RequestInit) => {
      signal = config.signal ?? undefined;
      return new Promise(() => undefined);
    });
    const { user, onApply } = draw();

    await pick(user, 'Shorten');
    await user.click(await screen.findByRole('button', { name: 'common.cancel' }));

    expect(signal?.aborted).toBe(true);
    expect(onApply).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });
});
