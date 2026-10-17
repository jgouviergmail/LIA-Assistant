/**
 * LIA's voices in the voice mode settings (ADR-345 amendment 2026-10-14): one
 * list per gender, each opening on the administrator's voice named; a change
 * saved at once with BOTH genders, so a quick second change never undoes the
 * first; a refusal said in the reader's words; nothing where LIA does not speak.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import type { LiaVoices } from '@/types/lia-voices';

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }));
vi.mock('@/lib/api-client', () => ({
  default: api,
  ApiError: class ApiError extends Error {},
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'proof-reader' } }) }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));
const sample = vi.hoisted(() => ({
  play: vi.fn(async () => undefined),
  replay: vi.fn(async () => undefined),
  stop: vi.fn(),
  status: 'idle' as 'idle' | 'loading' | 'playing' | 'error' | 'blocked',
  canReplay: false,
}));
vi.mock('@/hooks/useTtsVoiceSample', () => ({ useTtsVoiceSample: () => sample }));
const { i18n } = vi.hoisted(() => ({
  i18n: {
    t: (key: string, options?: Record<string, unknown>) =>
      options && 'name' in options ? `${key}|${String(options.name)}` : key,
    i18n: { language: 'fr', changeLanguage: () => undefined },
  },
}));
vi.mock('@/i18n/client', () => ({ useTranslation: () => i18n }));

import { LiaVoicesFields } from '../LiaVoicesFields';

const HENRI = { voice_id: 'h', label: 'Henri', gender: 'male', language: 'fr' };
const REMY = { voice_id: 'r', label: 'Rémy', gender: 'male', language: 'fr' };
const DENISE = { voice_id: 'd', label: 'Denise', gender: 'female', language: 'fr' };
const NEUTRAL = { voice_id: 'n', label: 'Alloy', gender: null, language: null };
const ARIA = { voice_id: 'a', label: 'Aria', gender: 'female', language: 'en' };

function lia(over: Partial<LiaVoices> = {}): LiaVoices {
  return {
    available: true,
    engine: 'fishaudio/s2.1-pro',
    provider: 'fishaudio',
    voices: [HENRI, REMY, DENISE, NEUTRAL],
    male: null,
    female: DENISE.voice_id,
    default_male: HENRI,
    default_female: DENISE,
    ...over,
  };
}

function maleList() {
  return screen.getByRole('combobox', { name: 'settings.voice_mode.lia_voices.male' });
}

function femaleList() {
  return screen.getByRole('combobox', { name: 'settings.voice_mode.lia_voices.female' });
}

beforeEach(() => {
  vi.clearAllMocks();
  sample.status = 'idle';
  sample.canReplay = false;
  api.get.mockResolvedValue(lia());
  api.put.mockImplementation(async (_url: string, choice: Record<string, string | null>) =>
    lia({ male: choice.male, female: choice.female })
  );
});

describe('LiaVoicesFields', () => {
  it('plays only an explicit choice, with its gender, without delaying or replacing its save', async () => {
    const { user } = renderWithProviders(<LiaVoicesFields lng="fr" />);
    await screen.findByRole('combobox', { name: /lia_voices\.male/ });
    expect(sample.play).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'settings.voice_sample.listen' })).toBeNull();

    await user.click(maleList());
    await user.click(screen.getByRole('option', { name: 'Rémy' }));
    expect(sample.play).toHaveBeenCalledWith({
      endpoint: '/voice/lia-voices/sample',
      payload: { gender: 'male', voice_id: 'r' },
    });
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/voice/lia-voices', { male: 'r', female: 'd' })
    );
    expect(maleList()).toHaveFocus();

    await user.click(femaleList());
    await user.click(
      screen.getByRole('option', { name: 'settings.voice_mode.lia_voices.default|Denise' })
    );
    expect(sample.play).toHaveBeenLastCalledWith({
      endpoint: '/voice/lia-voices/sample',
      payload: { gender: 'female', voice_id: null },
    });
  });

  it('keeps listening errors beside the controls, and replay never saves the voices again', async () => {
    sample.status = 'error';
    sample.canReplay = true;
    const { user } = renderWithProviders(<LiaVoicesFields lng="fr" />);
    expect(await screen.findByRole('alert')).toHaveTextContent('settings.voice_sample.failed');
    await user.click(screen.getByRole('button', { name: 'settings.voice_sample.listen' }));
    expect(sample.replay).toHaveBeenCalledOnce();
    expect(api.put).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('opens each list on the administrator’s voice, named, and shows the choice held', async () => {
    renderWithProviders(<LiaVoicesFields lng="fr" />);

    expect(await screen.findByText('settings.voice_mode.lia_voices.title')).toBeInTheDocument();
    expect(maleList()).toHaveTextContent('settings.voice_mode.lia_voices.default|Henri');
    expect(femaleList()).toHaveTextContent('Denise');
  });

  it('offers each gender its voices and those that name none', async () => {
    const { user } = renderWithProviders(<LiaVoicesFields lng="fr" />);

    await user.click(await screen.findByRole('combobox', { name: /lia_voices\.male/ }));
    const offered = screen.getAllByRole('option').map(option => option.textContent);

    expect(offered).toEqual([
      'settings.voice_mode.lia_voices.default|Henri',
      'Henri',
      'Rémy',
      'Alloy',
    ]);
  });

  it('saves both genders at once, the default as null', async () => {
    const { user } = renderWithProviders(<LiaVoicesFields lng="fr" />);

    await user.click(await screen.findByRole('combobox', { name: /lia_voices\.male/ }));
    await user.click(screen.getByRole('option', { name: 'Rémy' }));

    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/voice/lia-voices', { male: 'r', female: 'd' })
    );
    expect(toast.success).toHaveBeenCalledWith('settings.voice_mode.lia_voices.saved');

    await user.click(femaleList());
    await user.click(
      screen.getByRole('option', { name: 'settings.voice_mode.lia_voices.default|Denise' })
    );
    await waitFor(() =>
      expect(api.put).toHaveBeenLastCalledWith('/voice/lia-voices', { male: 'r', female: null })
    );
  });

  it('never undoes a change with the next one sent before its answer', async () => {
    let answer: (value: LiaVoices) => void = () => undefined;
    api.put.mockImplementationOnce(
      () =>
        new Promise<LiaVoices>(resolve => {
          answer = resolve;
        })
    );
    const { user } = renderWithProviders(<LiaVoicesFields lng="fr" />);

    await user.click(await screen.findByRole('combobox', { name: /lia_voices\.male/ }));
    await user.click(screen.getByRole('option', { name: 'Rémy' }));
    await user.click(femaleList());
    await user.click(screen.getByRole('option', { name: 'Alloy' }));

    expect(api.put).toHaveBeenCalledTimes(1);
    answer(lia({ male: 'r', female: 'd' }));
    await waitFor(() =>
      expect(api.put).toHaveBeenNthCalledWith(2, '/voice/lia-voices', { male: 'r', female: 'n' })
    );
    await waitFor(() => expect(femaleList()).toHaveTextContent('Alloy'));
  });

  it.each(['lia_voice_unknown', 'lia_voice_catalogue_unavailable'])(
    'says why %s was refused, in the reader’s words',
    async code => {
      api.put.mockRejectedValue(
        Object.assign(new Error('refused'), {
          status: 422,
          data: { detail: { code } },
        })
      );
      const { user } = renderWithProviders(<LiaVoicesFields lng="fr" />);

      await user.click(await screen.findByRole('combobox', { name: /lia_voices\.male/ }));
      await user.click(screen.getByRole('option', { name: 'Rémy' }));

      await waitFor(() =>
        expect(toast.error).toHaveBeenCalledWith(`settings.voice_mode.lia_voices.errors.${code}`)
      );
    }
  );

  it('narrows the lists to the reader’s language, keeping the voices held', async () => {
    api.get.mockResolvedValue(lia({ voices: [HENRI, DENISE, ARIA], female: ARIA.voice_id }));
    const { user } = renderWithProviders(<LiaVoicesFields lng="fr" />);

    const only = await screen.findByRole('switch', {
      name: 'settings.voice_language_filter.only_language',
    });
    expect(only).toBeChecked();
    await user.click(femaleList());
    // Aria is English, but the person holds her: she stays in the list.
    expect(screen.getAllByRole('option').map(option => option.textContent)).toContain('Aria');
  });

  it('keeps a voice held while the engine cannot list its voices, by its id', async () => {
    api.get.mockResolvedValue(lia({ voices: [], male: 'held-id', female: null }));
    renderWithProviders(<LiaVoicesFields lng="fr" />);

    expect(await screen.findByRole('combobox', { name: /lia_voices\.male/ })).toHaveTextContent(
      'held-id'
    );
  });

  it('shows nothing where LIA does not speak', async () => {
    api.get.mockResolvedValue(lia({ available: false }));
    const { container } = renderWithProviders(<LiaVoicesFields lng="fr" />);

    await waitFor(() => expect(api.get).toHaveBeenCalled());
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it('says the voices could not be read', async () => {
    api.get.mockRejectedValue(new Error('down'));
    renderWithProviders(<LiaVoicesFields lng="fr" />);

    expect(
      await screen.findByText('settings.voice_mode.lia_voices.unavailable')
    ).toBeInTheDocument();
  });
});
