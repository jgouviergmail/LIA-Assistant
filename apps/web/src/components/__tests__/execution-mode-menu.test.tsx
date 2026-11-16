/**
 * ExecutionModeMenu — the chat header's three modes (ADR-070, ADR-390).
 *
 * Rendered in real English and French: the oracles are what a person reads and
 * what a screen reader announces — the trigger naming the chosen mode, three
 * described choices with the chosen one checked, what « auto » does on THIS
 * instance, the outcome of a save — and that the keyboard reaches all of it.
 */
import { createInstance } from 'i18next';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import type { ExecutionModePreferenceState } from '@/hooks/useExecutionModePreference';

import en from '../../../locales/en/translation.json';
import fr from '../../../locales/fr/translation.json';

const language = createInstance();
await language.init({ lng: 'en', resources: { en: { translation: en }, fr: { translation: fr } } });
vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({ t: language.t, i18n: language }),
}));

const { preference } = vi.hoisted(() => {
  const holder: { current: ExecutionModePreferenceState | null } = { current: null };
  return { preference: holder };
});
vi.mock('@/hooks/useExecutionModePreference', () => ({
  useExecutionModePreference: (): ExecutionModePreferenceState => {
    if (!preference.current) throw new Error('call prefer() before rendering the menu');
    return preference.current;
  },
}));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { ExecutionModeMenu } from '../execution-mode-menu';

function prefer(over: Partial<ExecutionModePreferenceState> = {}): ExecutionModePreferenceState {
  preference.current = {
    mode: 'auto',
    autoResolution: 'decided',
    saving: null,
    refresh: vi.fn(async () => {}),
    choose: vi.fn(async () => 'saved' as const),
    ...over,
  };
  return preference.current;
}

beforeEach(async () => {
  vi.clearAllMocks();
  await language.changeLanguage('en');
});

describe('ExecutionModeMenu', () => {
  it('names the chosen mode on the trigger and wears its mark', () => {
    prefer({ mode: 'auto' });
    renderWithProviders(<ExecutionModeMenu lng="en" />);

    const trigger = screen.getByRole('button', { name: 'Execution: Automatic mode' });
    expect(trigger).toHaveAttribute('title', 'Execution: Automatic mode');
    expect(trigger.querySelector('.lucide-split')).not.toBeNull();
  });

  it('offers the three modes, each said with what it does, the chosen one checked', async () => {
    prefer({ mode: 'react' });
    const { user } = renderWithProviders(<ExecutionModeMenu lng="en" />);

    await user.click(screen.getByRole('button', { name: 'Execution: ReAct mode' }));
    const items = await screen.findAllByRole('menuitemradio');

    expect(items.map(item => item.getAttribute('aria-checked'))).toEqual([
      'false',
      'true',
      'false',
    ]);
    expect(items[0]).toHaveTextContent('Pipeline mode');
    expect(items[0]).toHaveTextContent('the most economical');
    expect(items[0].querySelector('.lucide-workflow')).not.toBeNull();
    expect(items[1]).toHaveTextContent('ReAct mode');
    expect(items[1]).toHaveTextContent('the most thorough');
    expect(items[2]).toHaveTextContent('Automatic mode');
    expect(items[2]).toHaveTextContent('LIA picks one of the two for each request');
  });

  it.each([
    ['always_react', 'On this server: always ReAct — the automatic choice is not set up'],
    ['always_pipeline', 'On this server: always Pipeline — ReAct is switched off'],
  ] as const)('says what « auto » does on an instance that %s', async (resolution, said) => {
    prefer({ mode: 'pipeline', autoResolution: resolution });
    const { user } = renderWithProviders(<ExecutionModeMenu lng="en" />);

    await user.click(screen.getByRole('button', { name: 'Execution: Pipeline mode' }));
    const auto = (await screen.findAllByRole('menuitemradio'))[2];

    expect(auto).toHaveTextContent(said);
    expect(auto).not.toHaveTextContent('LIA picks one of the two');
  });

  it('reads again what « auto » does each time it opens', async () => {
    const state = prefer();
    const { user } = renderWithProviders(<ExecutionModeMenu lng="en" />);

    await user.click(screen.getByRole('button', { name: 'Execution: Automatic mode' }));
    await screen.findAllByRole('menuitemradio');

    expect(state.refresh).toHaveBeenCalledTimes(1);
  });

  it('saves the choice and says so', async () => {
    const state = prefer({ mode: 'pipeline' });
    const { user } = renderWithProviders(<ExecutionModeMenu lng="en" />);

    await user.click(screen.getByRole('button', { name: 'Execution: Pipeline mode' }));
    await user.click(await screen.findByRole('menuitemradio', { name: /^Automatic mode/ }));

    expect(state.choose).toHaveBeenCalledWith('auto');
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Automatic mode enabled'));
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('says a save that failed failed', async () => {
    prefer({ mode: 'pipeline', choose: vi.fn(async () => 'failed' as const) });
    const { user } = renderWithProviders(<ExecutionModeMenu lng="en" />);

    await user.click(screen.getByRole('button', { name: 'Execution: Pipeline mode' }));
    await user.click(await screen.findByRole('menuitemradio', { name: /^ReAct mode/ }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('says nothing when there was nothing to send', async () => {
    prefer({ mode: 'pipeline', choose: vi.fn(async () => 'ignored' as const) });
    const { user } = renderWithProviders(<ExecutionModeMenu lng="en" />);

    await user.click(screen.getByRole('button', { name: 'Execution: Pipeline mode' }));
    await user.click(await screen.findByRole('menuitemradio', { name: /^Pipeline mode/ }));

    expect(toast.success).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('stays focusable and says it is busy while a save is on its way', () => {
    prefer({ mode: 'pipeline', saving: 'react' });
    renderWithProviders(<ExecutionModeMenu lng="en" />);

    const trigger = screen.getByRole('button', { name: 'Execution: Pipeline mode' });
    expect(trigger).toHaveAttribute('aria-busy', 'true');
    expect(trigger).not.toBeDisabled();
  });

  it('is reached, used and left with the keyboard alone', async () => {
    const state = prefer({ mode: 'pipeline' });
    const { user } = renderWithProviders(<ExecutionModeMenu lng="en" />);
    const trigger = screen.getByRole('button', { name: 'Execution: Pipeline mode' });

    await user.tab();
    expect(trigger).toHaveFocus();
    await user.keyboard('{Enter}');
    const menu = await screen.findByRole('menu');
    await waitFor(() =>
      expect(within(menu).getAllByRole('menuitemradio')).toContain(document.activeElement)
    );
    await user.keyboard('{ArrowDown}{ArrowDown}{Enter}');

    await waitFor(() => expect(state.choose).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it('speaks the reader’s language', async () => {
    await language.changeLanguage('fr');
    prefer({ mode: 'auto' });

    renderWithProviders(<ExecutionModeMenu lng="fr" />);

    expect(
      screen.getByRole('button', { name: 'Exécution : Mode automatique' })
    ).toBeInTheDocument();
  });
});
