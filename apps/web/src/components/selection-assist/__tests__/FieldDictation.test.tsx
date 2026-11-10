import { act, fireEvent, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { useState, useLayoutEffect } from 'react';
import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { UseVoiceInputOptions } from '@/hooks/useVoiceInput';
import type { AppConfig } from '@/hooks/useAppConfig';
import type { Language } from '@/i18n/settings';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import { SelectionAssistProvider } from '../SelectionAssistProvider';

const state = vi.hoisted(() => ({
  owner: 'one' as string | null,
  path: '/en/dashboard',
  enabled: true,
  supported: true,
  voice: null as UseVoiceInputOptions | null,
  onLayout: null as (() => void) | null,
  start: vi.fn(),
  stop: vi.fn(),
}));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: state.owner ? { id: state.owner, is_active: true } : null }),
}));
vi.mock('next/navigation', () => ({
  usePathname: () => state.path,
  useRouter: () => ({ push: vi.fn() }),
}));
vi.mock('@/hooks/useApplicationAccountQuery', () => ({
  useApplicationAccountQuery: () => ({ data: undefined, error: null }),
}));
vi.mock('@/hooks/useAppConfig', () => ({
  useAppConfig: () => ({
    config: { capabilities: { stt: { enabled: state.enabled, family: 'voice' } } } satisfies Pick<
      AppConfig,
      'capabilities'
    >,
    error: null,
  }),
}));
vi.mock('@/hooks/useVoiceInput', () => ({
  canRecordVoice: () => state.supported,
  useVoiceInput: (options: UseVoiceInputOptions) => {
    state.voice = options;
    return { isRecording: true, startRecording: state.start, stopRecording: state.stop };
  },
}));
vi.mock('@/i18n/client', () => ({
  useTranslation: (lng: Language) => ({
    t: (key: string) => {
      let value: unknown = lng === 'fr' ? fr : en;
      for (const part of key.split('.')) {
        if (!value || typeof value !== 'object') return key;
        value = Reflect.get(value, part);
      }
      return typeof value === 'string' ? value : key;
    },
  }),
}));

const DICTATE = en.selectionAssist.voice.dictate;
const STOP = en.selectionAssist.voice.stop_dictation;
function draw(lng: Language = 'en') {
  function Fields() {
    const [show, setShow] = useState(true);
    useLayoutEffect(() => {
      state.onLayout?.();
    });
    return (
      <>
        {show && <textarea aria-label="First" />}
        <textarea aria-label="Second" />
        <button type="button">Elsewhere</button>
        <button type="button" onClick={() => setShow(false)}>
          Remove first
        </button>
      </>
    );
  }
  const content = () => (
    <SelectionAssistProvider lng={lng}>
      <Fields />
    </SelectionAssistProvider>
  );
  const view = renderWithProviders(content());
  const first = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'First' });
  act(() => first.focus());
  return { ...view, first, refresh: () => view.rerender(content()) };
}
beforeEach(() => {
  vi.clearAllMocks();
  Object.assign(state, {
    owner: 'one',
    path: '/en/dashboard',
    enabled: true,
    supported: true,
    voice: null,
    onLayout: null,
  });
  window.getSelection()?.removeAllRanges();
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(
    new DOMRect(40, 200, 120, 30)
  );
});

it('offers dictation in a focused empty field even without text assists, and starts only on a click', async () => {
  const { user, first } = draw();
  const button = await screen.findByRole('button', { name: DICTATE });
  expect(document.activeElement).toBe(first);
  expect(state.start).not.toHaveBeenCalled();
  expect(within(screen.getByRole('toolbar')).getAllByRole('button')).toHaveLength(2);
  await user.click(button);
  await waitFor(() => expect(state.start).toHaveBeenCalledOnce());
  await user.click(screen.getByRole('button', { name: STOP }));
  expect(state.stop).toHaveBeenCalledOnce();
});

it('keeps dictation available after ordinary typing at the focused caret', async () => {
  const { user, first } = draw();
  await screen.findByRole('button', { name: DICTATE });
  await user.keyboard('A');
  expect(first.value).toBe('A');
  expect(await screen.findByRole('button', { name: DICTATE })).toBeVisible();
  expect(first).toHaveFocus();
  expect(state.start).not.toHaveBeenCalled();
});

it('recognizes a field focused before capability metadata becomes available', async () => {
  state.enabled = false;
  const { first, refresh } = draw();
  expect(first).toHaveFocus();
  await act(async () => {
    await new Promise(resolve => setTimeout(resolve, 220));
  });
  state.enabled = true;
  refresh();
  expect(await screen.findByRole('button', { name: DICTATE })).toBeVisible();
});

it('inserts dictated words at the frozen caret through native editing and returns focus', async () => {
  const { user, first } = draw();
  act(() => {
    first.value = ', friend';
    first.setSelectionRange(0, 0);
    fireEvent.input(first);
  });
  await user.click(await screen.findByRole('button', { name: DICTATE }));
  await waitFor(() => expect(state.start).toHaveBeenCalledOnce());
  const command = vi.fn((_command: string, _ui: boolean, text: string) => {
    first.setRangeText(text);
    first.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  });
  Object.defineProperty(document, 'execCommand', { configurable: true, value: command });
  try {
    act(() => state.voice?.onTranscription?.('Hello'));
    expect(first.value).toBe('Hello, friend');
    expect(command).toHaveBeenCalledWith('insertText', false, 'Hello');
    expect(document.activeElement).toBe(first);
    await waitFor(() => expect(screen.queryByRole('toolbar')).not.toBeInTheDocument());
  } finally {
    Reflect.deleteProperty(document, 'execCommand');
  }
});

it.each(['limit', 'unsupported'] as const)(
  'keeps dictated words available to copy if native insertion refuses them (%s)',
  async reason => {
    const { user, first } = draw();
    if (reason === 'limit') first.maxLength = 3;
    await user.click(await screen.findByRole('button', { name: DICTATE }));
    await waitFor(() => expect(state.start).toHaveBeenCalledOnce());
    act(() => state.voice?.onTranscription?.('Keep these words'));
    const answer = await screen.findByRole('dialog', { name: DICTATE });
    expect(within(answer).getByText('Keep these words')).toBeVisible();
    expect(first.value).toBe('');
    await user.click(within(answer).getByRole('button', { name: en.selectionAssist.copy }));
    expect(await navigator.clipboard.readText()).toBe('Keep these words');
    await user.click(within(answer).getByRole('button', { name: en.common.close }));
    expect(first).toHaveFocus();
    expect(screen.queryByRole('dialog', { name: DICTATE })).not.toBeInTheDocument();
  }
);

it.each(['en', 'fr'] as const)(
  'names the caret control in %s and supports keyboard dismissal',
  async lng => {
    const { user, first } = draw(lng);
    const words = lng === 'fr' ? fr : en;
    const button = await screen.findByRole('button', { name: words.selectionAssist.voice.dictate });
    expect(first).toHaveFocus();
    await user.keyboard('{Alt>}{Enter}{/Alt}');
    expect(button).toHaveFocus();
    await user.keyboard('{End}');
    expect(screen.getByRole('button', { name: words.common.close })).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(first).toHaveFocus();
    expect(screen.queryByRole('toolbar')).not.toBeInTheDocument();
    expect(state.start).not.toHaveBeenCalled();
  }
);

it('closes on a different field and rejects words arriving for the old one', async () => {
  const { user, first } = draw();
  await user.click(await screen.findByRole('button', { name: DICTATE }));
  await waitFor(() => expect(state.start).toHaveBeenCalledOnce());
  const late = state.voice?.onTranscription;
  const second = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Second' });
  act(() => second.focus());
  expect(screen.queryByRole('button', { name: STOP })).not.toBeInTheDocument();
  act(() => late?.('Stale words'));
  expect(first.value).toBe('');
  expect(second.value).toBe('');
  expect(document.activeElement).toBe(second);
  expect(await screen.findByRole('button', { name: DICTATE })).toBeVisible();
  act(() => screen.getByRole('button', { name: 'Elsewhere' }).focus());
  await waitFor(() => expect(screen.queryByRole('toolbar')).not.toBeInTheDocument());
});

it.each(['account', 'route', 'capability'] as const)(
  'retires pending words when the %s changes',
  async reason => {
    const { user, first, refresh } = draw();
    await user.click(await screen.findByRole('button', { name: DICTATE }));
    await waitFor(() => expect(state.start).toHaveBeenCalledOnce());
    const late = state.voice?.onTranscription;
    if (reason === 'account') state.owner = 'another';
    if (reason === 'route') state.path = '/en/dashboard/settings';
    if (reason === 'capability') state.enabled = false;
    refresh();
    expect(screen.queryByRole('button', { name: STOP })).not.toBeInTheDocument();
    act(() => late?.('Belongs to the retired field'));
    expect(first.value).toBe('');
  }
);

it.each(['readonly', 'detached', 'changed'] as const)(
  'withdraws recording when its field is %s',
  async cause => {
    const { user, first } = draw();
    await user.click(await screen.findByRole('button', { name: DICTATE }));
    await waitFor(() => expect(state.start).toHaveBeenCalledOnce());
    await act(async () => {
      if (cause === 'readonly') first.readOnly = true;
      if (cause === 'detached')
        fireEvent.click(screen.getByRole('button', { name: 'Remove first' }));
      if (cause === 'changed') fireEvent.input(first, { target: { value: 'New words' } });
    });
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: STOP })).not.toBeInTheDocument()
    );
  }
);

it.each(['capability', 'browser', 'account'] as const)(
  'offers nothing when %s forbids recording',
  async reason => {
    if (reason === 'capability') state.enabled = false;
    if (reason === 'browser') state.supported = false;
    if (reason === 'account') state.owner = null;
    draw();
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 220));
    });
    expect(screen.queryByRole('button', { name: DICTATE })).not.toBeInTheDocument();
    expect(state.start).not.toHaveBeenCalled();
  }
);

it('rejects a late transcription during the account-switch commit before passive cleanup', async () => {
  const { user, first, refresh } = draw();
  await user.click(await screen.findByRole('button', { name: DICTATE }));
  await waitFor(() => expect(state.start).toHaveBeenCalledOnce());
  const late = state.voice?.onTranscription;
  const command = vi.fn((_command: string, _ui: boolean, text: string) => {
    first.setRangeText(text);
    first.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  });
  Object.defineProperty(document, 'execCommand', { configurable: true, value: command });
  try {
    state.owner = 'another';
    state.onLayout = () => late?.('Old account words');
    refresh();
    expect(command).not.toHaveBeenCalled();
    expect(first.value).toBe('');
  } finally {
    state.onLayout = null;
    Reflect.deleteProperty(document, 'execCommand');
  }
});
