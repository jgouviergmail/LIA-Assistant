import { act, fireEvent, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { SelectionContext } from '../context';
import { SelectionHost } from '../SelectionHost';
import { createSelectionStore } from '@/lib/selection-assist/store';
import { captureSelection } from '@/lib/selection-assist/targets';
const { request } = vi.hoisted(() => ({ request: vi.fn() }));
const { speak, askLia } = vi.hoisted(() => ({ speak: vi.fn(), askLia: vi.fn() }));
vi.mock('@/components/workbench/assist/useAskLia', () => ({ useAskLia: () => askLia }));
vi.mock('@/lib/selection-assist/speech', () => ({ requestReadAloud: speak }));
vi.mock('@/lib/selection-assist/transport', () => ({ requestSelection: request }));
vi.mock('@/i18n/client', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
const offer = {
  text_max_chars: 1000,
  question_max_chars: 100,
  language_max_chars: 40,
  internet_available: true,
  read_aloud_available: true,
  internet_timeout_seconds: 360,
  call_timeout_seconds: 120,
  heartbeat_seconds: 10,
  destinations: [],
};

function mount(modal = false, internetAvailable = true) {
  const store = createSelectionStore();
  const send = vi.fn();
  const field = <textarea aria-label="source" defaultValue="Hello world" />;
  const view = renderWithProviders(
    <SelectionContext.Provider
      value={{
        store,
        lng: 'en',
        dictates: false,
        offer: { ...offer, internet_available: internetAvailable },
      }}
    >
      <form
        onSubmit={event => {
          event.preventDefault();
          send();
        }}
      >
        {modal ? (
          <Dialog open>
            <DialogContent>
              <DialogTitle>Editor</DialogTitle>
              <DialogDescription>Write here</DialogDescription>
              {field}
            </DialogContent>
          </Dialog>
        ) : (
          field
        )}
      </form>
      <SelectionHost id={null} />
    </SelectionContext.Provider>
  );
  const input = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'source' });
  input.focus();
  input.setSelectionRange(0, 5);
  act(() => store.set(captureSelection(document)));
  return { ...view, store, send, input };
}
beforeEach(() => {
  request.mockReset();
  speak.mockReset();
  askLia.mockReset();
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(
    new DOMRect(40, 200, 120, 30)
  );
});
describe('the shared selection layer', () => {
  it('claims a paid click before React can remove its original toolbar', async () => {
    request.mockImplementation(() => new Promise(() => {}));
    mount();
    const button = await screen.findByRole('button', { name: 'selectionAssist.actions.fix' });
    act(() => {
      fireEvent.click(button);
      fireEvent.click(button);
    });
    expect(request).toHaveBeenCalledOnce();
  });
  it('offers the requested reading order, including Internet after translation', async () => {
    const { input, store } = mount();
    input.readOnly = true;
    act(() => store.set(captureSelection(document)));
    const toolbar = await screen.findByRole('toolbar');
    expect(
      within(toolbar)
        .getAllByRole('button')
        .map(button => button.textContent)
        .filter(Boolean)
    ).toEqual(
      [
        'read',
        'ask',
        'explain',
        'summarize',
        'simplify',
        'translate',
        'internet',
        'task',
        'event',
        'reminder',
        'ticket',
        'memory',
        'lia',
      ].map(action => `selectionAssist.actions.${action}`)
    );
  });
  it('hands the selected words to the existing chat draft door without a model call', async () => {
    const { input, store, user } = mount();
    input.readOnly = true;
    act(() => store.set(captureSelection(document)));
    await user.click(await screen.findByRole('button', { name: 'selectionAssist.actions.lia' }));
    expect(askLia).toHaveBeenCalledExactlyOnceWith('Hello');
    expect(store.getSnapshot()).toBeNull();
    expect(request).not.toHaveBeenCalled();
    expect(speak).not.toHaveBeenCalled();
  });
  it('reads the exact selection through the existing speech door and shows a declared cut', async () => {
    speak.mockResolvedValue({ audio: 'SUQz', cut: true, cost_eur: 0.002, usage: null });
    const { input, store, user } = mount();
    input.readOnly = true;
    act(() => store.set(captureSelection(document)));
    await user.click(await screen.findByRole('button', { name: 'selectionAssist.actions.read' }));
    expect(
      await screen.findByLabelText('selectionAssist.actions.read', { selector: 'audio' })
    ).toHaveAttribute('src', 'data:audio/mpeg;base64,SUQz');
    expect(screen.getByText('workbench.assist.voice.read_cut')).toBeVisible();
    expect(speak).toHaveBeenCalledWith(
      '/tool-assists/read-aloud',
      { text: 'Hello' },
      expect.any(AbortSignal)
    );
    expect(request).not.toHaveBeenCalled();
  });
  it('cancels a read-aloud request on dismissal and ignores its late audio', async () => {
    let signal: AbortSignal | undefined;
    speak.mockImplementation((_path: string, _body: object, incoming: AbortSignal) => {
      signal = incoming;
      return new Promise(() => {});
    });
    const { input, store, user } = mount();
    input.readOnly = true;
    act(() => store.set(captureSelection(document)));
    await user.click(await screen.findByRole('button', { name: 'selectionAssist.actions.read' }));
    expect(screen.getByRole('status')).toHaveTextContent('selectionAssist.waiting_read');
    expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true');
    await user.click(screen.getByRole('button', { name: 'common.close' }));
    expect(signal?.aborted).toBe(true);
    expect(screen.queryByLabelText('selectionAssist.actions.read')).not.toBeInTheDocument();
  });
  it('does not spend on Internet when no search capability is available', async () => {
    const { input, store, user } = mount(false, false);
    input.readOnly = true;
    act(() => store.set(captureSelection(document)));
    const action = await screen.findByRole('button', { name: 'selectionAssist.actions.internet' });
    expect(action).toHaveAttribute('aria-disabled', 'true');
    await user.click(action);
    expect(request).not.toHaveBeenCalled();
  });
  it('shows an empty successful research result explicitly', async () => {
    request.mockResolvedValue({
      proposal: {
        kind: 'research',
        query: 'Missing subject',
        provider: 'wikipedia',
        summary: null,
        sources: [],
      },
      usage: null,
    });
    const { input, store, user } = mount();
    input.readOnly = true;
    act(() => store.set(captureSelection(document)));
    await user.click(
      await screen.findByRole('button', { name: 'selectionAssist.actions.internet' })
    );
    expect(await screen.findByRole('status')).toHaveTextContent('selectionAssist.no_sources');
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });
  it('offers no contextual action at a caret or in an empty field', async () => {
    const { input, store } = mount();
    input.value = '';
    input.setSelectionRange(0, 0);
    act(() => store.set(captureSelection(document)));
    await waitFor(() => expect(screen.queryByRole('toolbar')).not.toBeInTheDocument());
    expect(request).not.toHaveBeenCalled();
  });
  it('offers the six editing actions in reading order, without microphone capture', async () => {
    mount();
    const toolbar = await screen.findByRole('toolbar');
    expect(
      within(toolbar)
        .getAllByRole('button')
        .map(button => button.textContent)
        .filter(Boolean)
    ).toEqual(
      ['translate', 'fix', 'format', 'shorter', 'formal', 'warm'].map(
        action => `selectionAssist.actions.${action}`
      )
    );
    expect(
      screen.queryByRole('button', { name: 'selectionAssist.actions.dictate' })
    ).not.toBeInTheDocument();
  });
  it('offers Internet on a readonly selection and keeps the returned sources in the bubble', async () => {
    request.mockResolvedValue({
      proposal: {
        kind: 'research',
        query: 'Greeting history',
        provider: 'brave',
        summary: null,
        sources: [
          {
            title: 'A source',
            url: 'https://example.test/greeting',
            excerpt: 'A documented greeting.',
          },
        ],
      },
      usage: null,
    });
    const { user, input, store } = mount();
    input.readOnly = true;
    act(() => store.set(captureSelection(document)));
    await user.click(
      await screen.findByRole('button', { name: 'selectionAssist.actions.internet' })
    );
    expect(await screen.findByRole('link', { name: 'A source' })).toHaveAttribute(
      'href',
      'https://example.test/greeting'
    );
    expect(screen.getByText('A documented greeting.')).toBeVisible();
    expect(request.mock.calls[0][1]).toEqual({
      mode: 'read',
      action: 'internet',
      text: 'Hello',
      origin: 'page',
    });
    expect(screen.queryByRole('button', { name: 'selectionAssist.apply' })).not.toBeInTheDocument();
  });
  it.each([false, true])(
    'asks for a target language before translating (readonly=%s)',
    async readOnly => {
      request.mockResolvedValue({ proposal: { kind: 'text', text: 'Hola' }, usage: null });
      const { user, store, input, send } = mount(true);
      input.readOnly = readOnly;
      act(() => store.set(captureSelection(document)));
      await user.click(
        await screen.findByRole('button', { name: 'selectionAssist.actions.translate' })
      );
      expect(request).not.toHaveBeenCalled();
      await user.click(screen.getByRole('button', { name: 'Spanish' }));
      expect(screen.getByRole('textbox', { name: 'selectionAssist.target_language' })).toHaveValue(
        'Spanish'
      );
      await user.click(screen.getByRole('button', { name: 'selectionAssist.send' }));
      expect(await screen.findByText('Hola')).toBeVisible();
      expect(request).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({ text: 'Hello', action: 'translate', target_language: 'Spanish' }),
        expect.any(AbortSignal),
        offer
      );
      expect(send).not.toHaveBeenCalled();
      expect(input.value).toBe('Hello world');
    }
  );

  it('keeps a freely named language on explicit retry, and never submits a blank language', async () => {
    request
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({ proposal: { kind: 'text', text: 'こんにちは' }, usage: null });
    const { user } = mount();
    await user.click(
      await screen.findByRole('button', { name: 'selectionAssist.actions.translate' })
    );
    await user.click(screen.getByRole('button', { name: 'selectionAssist.send' }));
    expect(request).not.toHaveBeenCalled();
    await user.type(
      screen.getByRole('textbox', { name: 'selectionAssist.target_language' }),
      'Japanese'
    );
    await user.click(screen.getByRole('button', { name: 'selectionAssist.send' }));
    await user.click(await screen.findByRole('button', { name: 'common.retry' }));
    expect(await screen.findByText('こんにちは')).toBeVisible();
    expect(request).toHaveBeenCalledTimes(2);
    for (const [, body] of request.mock.calls)
      expect(body).toMatchObject({ target_language: 'Japanese' });
  });

  it('formats only the selected words and leaves applying the proposal explicit', async () => {
    request.mockResolvedValue({
      proposal: { kind: 'text', text: 'A clear paragraph.' },
      usage: null,
    });
    const { user, input } = mount();
    await user.click(await screen.findByRole('button', { name: 'selectionAssist.actions.format' }));
    expect(await screen.findByText('A clear paragraph.')).toBeVisible();
    expect(request.mock.calls[0][1]).toEqual({
      mode: 'edit',
      action: 'format',
      text: 'Hello',
      origin: 'page',
    });
    expect(input.value).toBe('Hello world');
    expect(screen.getByRole('button', { name: 'selectionAssist.apply' })).toBeVisible();
  });

  it('gives an answer a concrete control when the browser parks focus on the dialog itself', async () => {
    let answer: (value: { proposal: { kind: 'text'; text: string }; usage: null }) => void = () =>
      undefined;
    request.mockImplementation(
      () =>
        new Promise(resolve => {
          answer = resolve;
        })
    );
    const { user, input, store } = mount();
    input.readOnly = true;
    act(() => store.set(captureSelection(document)));
    await user.click(await screen.findByRole('button', { name: 'selectionAssist.actions.ask' }));
    await user.type(screen.getByRole('textbox', { name: 'selectionAssist.question' }), 'Meaning?');
    await user.click(screen.getByRole('button', { name: 'selectionAssist.send' }));
    const dialog = screen.getByRole('dialog', { name: 'selectionAssist.actions.ask' });
    dialog.focus();
    await act(async () => answer({ proposal: { kind: 'text', text: 'Greeting' }, usage: null }));
    await waitFor(() =>
      expect(within(dialog).getByRole('button', { name: 'common.close' })).toHaveFocus()
    );
  });
  it('returns focus to the readable surface when a selected span cannot take focus', async () => {
    const store = createSelectionStore();
    const { user } = renderWithProviders(
      <SelectionContext.Provider value={{ store, lng: 'en', offer, dictates: false }}>
        <article tabIndex={-1} aria-label="Source">
          <span>Selected sentence</span>
        </article>
        <SelectionHost id={null} />
      </SelectionContext.Provider>
    );
    const range = document.createRange();
    range.selectNodeContents(screen.getByText('Selected sentence'));
    document.getSelection()?.removeAllRanges();
    document.getSelection()?.addRange(range);
    act(() => store.set(captureSelection(document)));
    await user.click(await screen.findByRole('button', { name: 'selectionAssist.actions.ask' }));
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(screen.getByRole('article', { name: 'Source' })).toHaveFocus();
  });
  it('a modal owns its toolbar and a nested bubble, without sending the outer form', async () => {
    request.mockResolvedValue({ proposal: { kind: 'text', text: 'Greeting' }, usage: null });
    const { user, store, input, send } = mount(true);
    // A readonly selection asks a question instead of editing it.
    input.readOnly = true;
    act(() => store.set(captureSelection(document)));
    await user.click(await screen.findByRole('button', { name: 'selectionAssist.actions.ask' }));
    const question = screen.getByRole('textbox', { name: 'selectionAssist.question' });
    await user.type(question, 'Meaning?');
    await user.click(screen.getByRole('button', { name: 'selectionAssist.send' }));
    expect(await screen.findByText('Greeting')).toBeVisible();
    expect(
      within(screen.getByRole('dialog', { name: 'selectionAssist.actions.ask' })).getByRole(
        'button',
        { name: 'common.close' }
      )
    ).toHaveFocus();
    expect(send).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog', { name: 'Editor' })).toBeVisible();
    expect(request).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ text: 'Hello', question: 'Meaning?' }),
      expect.any(AbortSignal),
      offer
    );
  });
  it('never replaces a field that changed during the request, and cancels the request', async () => {
    let signal: AbortSignal | null = null;
    request.mockImplementation((_path: string, _body: object, incoming: AbortSignal) => {
      signal = incoming;
      return new Promise(() => {});
    });
    const { user, input } = mount();
    await user.click(await screen.findByRole('button', { name: 'selectionAssist.actions.fix' }));
    fireEvent.input(input, { target: { value: 'My new text' } });
    await waitFor(() => expect(signal?.aborted).toBe(true));
    expect(input.value).toBe('My new text');
    expect(screen.getByRole('status')).toHaveTextContent('selectionAssist.stale');
  });
});
