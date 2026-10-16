/**
 * AdminVoiceLibrarySection — the instance's Fish Audio voice library (ADR-345).
 *
 * The hook is real; only the network is replaced (the API client for JSON,
 * `fetch` for the two multipart routes). What is asserted is what an
 * administrator's act sends, and what the page says back: a voice a slot
 * speaks with is never sent for deletion, a clone leaves only under the
 * attestation, a design's candidates are listened to before one is saved.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import type { DesignResult, LibraryVoice, VoiceLibrary } from '@/types/voice-library';

const { get, post, patch, del, toast } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn() },
}));
vi.mock('@/lib/api-client', () => {
  class ApiError extends Error {
    constructor(
      message: string,
      public status: number,
      public data?: unknown
    ) {
      super(message);
    }
  }
  return {
    default: { get, post, patch, delete: del },
    ApiError,
    apiEndpointUrl: (endpoint: string) => `https://api.test${endpoint}`,
  };
});
vi.mock('sonner', () => ({ toast }));
// The global stub echoes the key; this one also shows the slots a sentence names.
const { i18n } = vi.hoisted(() => ({
  i18n: {
    t: (key: string, options?: { slots?: string }) =>
      options?.slots ? `${key}|${options.slots}` : key,
    i18n: { language: 'en', changeLanguage: () => undefined },
  },
}));
vi.mock('@/i18n/client', () => ({ useTranslation: () => i18n }));

import AdminVoiceLibrarySection from '../AdminVoiceLibrarySection';

const KEY = 'settings.admin.voiceLibrary';

function voice(over: Partial<LibraryVoice> = {}): LibraryVoice {
  return {
    voice_id: 'a'.repeat(32),
    title: 'Narrator',
    state: 'trained',
    languages: ['fr'],
    created_at: '2026-10-14T08:00:00Z',
    used_by_slots: [],
    ...over,
  };
}

function library(over: Partial<VoiceLibrary> = {}): VoiceLibrary {
  return {
    configured: true,
    creation_enabled: true,
    prefill_available: false,
    design_cost_usd: 0.01,
    candidate_ttl_seconds: 1800,
    voices: [voice()],
    bounds: {
      samples_max: 5,
      sample_max_bytes: 10 * 1024 * 1024,
      total_max_bytes: 20 * 1024 * 1024,
      sample_extensions: ['wav', 'mp3', 'm4a', 'opus'],
      title_max_chars: 100,
      instruction_max_chars: 2000,
      preview_max_chars: 150,
      candidates_max: 4,
      prefill_max_seconds: 120,
    },
    ...over,
  };
}

const fetchMock = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  get.mockResolvedValue(library());
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function reply(status: number, body: unknown) {
  return { ok: status < 400, status, json: async () => body };
}

async function rendered(data: VoiceLibrary = library()) {
  get.mockResolvedValue(data);
  const view = renderWithProviders(<AdminVoiceLibrarySection lng="en" />);
  await screen.findByText(`${KEY}.list.title`);
  return view;
}

describe('AdminVoiceLibrarySection — the voices', () => {
  it('keeps unknown vendor language labels visible beside known languages', async () => {
    await rendered(library({ voices: [voice({ languages: ['fr', 'constructor', '__proto__'] })] }));

    expect(screen.getByText(/Français.*constructor.*__proto__/)).toBeInTheDocument();
  });

  it('never sends a voice a slot speaks with for deletion, and says which slot', async () => {
    const { user } = await rendered(library({ voices: [voice({ used_by_slots: ['voice_tts'] })] }));

    expect(screen.getByText(new RegExp(`${KEY}.list.usedBy`))).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: `${KEY}.list.delete` }));

    expect(del).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith(`${KEY}.list.inUse|${KEY}.slots.voice_tts`);
  });

  it('deletes a free voice once confirmed, then reads the library again', async () => {
    del.mockResolvedValue(undefined);
    const { user } = await rendered();

    await user.click(screen.getByRole('button', { name: `${KEY}.list.delete` }));
    const dialog = await screen.findByRole('alertdialog');
    await user.click(within(dialog).getByRole('button', { name: `${KEY}.list.deleteConfirm` }));

    await waitFor(() =>
      expect(del).toHaveBeenCalledWith(`/admin/voice/fishaudio/library/${'a'.repeat(32)}`)
    );
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    expect(toast.success).toHaveBeenCalledWith(`${KEY}.list.deleted`);
  });

  it('says the key is missing rather than offering forms that cannot work', async () => {
    get.mockResolvedValue(library({ configured: false, voices: [] }));
    renderWithProviders(<AdminVoiceLibrarySection lng="en" />);

    expect(await screen.findByText(`${KEY}.notConfigured`)).toBeInTheDocument();
    expect(screen.queryByText(`${KEY}.clone.title`)).toBeNull();
  });

  it('shows a failed refresh after a confirmed deletion while keeping forms mounted', async () => {
    const { ApiError } = await import('@/lib/api-client');
    del.mockResolvedValue(undefined);
    const { user } = await rendered();
    get.mockRejectedValueOnce(
      new ApiError('Catalogue unavailable', 503, { detail: { code: 'fishaudio_unavailable' } })
    );

    await user.click(screen.getByRole('button', { name: `${KEY}.list.delete` }));
    const dialog = await screen.findByRole('alertdialog');
    await user.click(within(dialog).getByRole('button', { name: `${KEY}.list.deleteConfirm` }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      `${KEY}.errors.fishaudio_unavailable`
    );
    expect(del).toHaveBeenCalledTimes(1);
    expect(toast.success).toHaveBeenCalledWith(`${KEY}.list.deleted`);
    expect(screen.getByText(`${KEY}.clone.title`)).toBeInTheDocument();
  });

  it('keeps the voices manageable when the operator switched creation off', async () => {
    await rendered(library({ creation_enabled: false }));

    expect(screen.getByText(`${KEY}.creationDisabled`)).toBeInTheDocument();
    expect(screen.queryByText(`${KEY}.clone.title`)).toBeNull();
    expect(screen.queryByText(`${KEY}.design.title`)).toBeNull();
    expect(screen.getByRole('button', { name: `${KEY}.list.rename` })).toBeInTheDocument();
  });
});

describe('AdminVoiceLibrarySection — a clone', () => {
  const wav = (name: string) => new File(['RIFF'], name, { type: 'audio/wav' });

  it('leaves nothing without the attestation', async () => {
    const { user } = await rendered();

    await user.type(screen.getByLabelText(`${KEY}.clone.nameLabel`), 'My voice');
    await user.upload(screen.getByLabelText(`${KEY}.clone.samplesLabel`), wav('a.wav'));
    await user.click(screen.getByRole('button', { name: `${KEY}.clone.submit` }));

    expect(fetchMock).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith(`${KEY}.clone.problems.consent`);
  });

  it('sends the recordings, their transcripts and the attestation, then reads the library again', async () => {
    fetchMock.mockResolvedValue(reply(201, voice({ title: 'My voice' })));
    const { user } = await rendered();

    await user.type(screen.getByLabelText(`${KEY}.clone.nameLabel`), 'My voice');
    await user.upload(screen.getByLabelText(`${KEY}.clone.samplesLabel`), [
      wav('a.wav'),
      wav('b.wav'),
    ]);
    const transcripts = screen.getAllByLabelText(`${KEY}.clone.transcriptLabel`);
    await user.type(transcripts[0], 'First clip.');
    await user.type(transcripts[1], 'Second clip.');
    await user.click(screen.getByLabelText(`${KEY}.clone.consentLabel`));
    await user.click(screen.getByRole('button', { name: `${KEY}.clone.submit` }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('https://api.test/admin/voice/fishaudio/library/clone');
    const body = init.body as FormData;
    expect(body.get('title')).toBe('My voice');
    expect(body.get('consent')).toBe('true');
    expect(body.getAll('samples')).toHaveLength(2);
    expect(body.getAll('texts')).toEqual(['First clip.', 'Second clip.']);
    expect(init.credentials).toBe('include');
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    expect(toast.success).toHaveBeenCalledWith(`${KEY}.clone.cloned`);
  });

  it('names a refusal by its code', async () => {
    fetchMock.mockResolvedValue(reply(402, { detail: { code: 'fishaudio_payment_required' } }));
    const { user } = await rendered();

    await user.type(screen.getByLabelText(`${KEY}.clone.nameLabel`), 'My voice');
    await user.upload(screen.getByLabelText(`${KEY}.clone.samplesLabel`), wav('a.wav'));
    await user.click(screen.getByLabelText(`${KEY}.clone.consentLabel`));
    await user.click(screen.getByRole('button', { name: `${KEY}.clone.submit` }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(`${KEY}.errors.fishaudio_payment_required`)
    );
  });
});

describe('AdminVoiceLibrarySection — a design', () => {
  const result: DesignResult = {
    candidates: [
      {
        candidate_id: '0'.repeat(32),
        duration_ms: 3100,
        text: 'Hello.',
        language: 'en',
        audio_base64: 'UklGRg==',
      },
    ],
    cost_usd: 0.01,
    expires_in_seconds: 1800,
  };

  it('asks for candidates, plays them, and saves the one named', async () => {
    post.mockResolvedValueOnce(result).mockResolvedValueOnce(voice({ title: 'Warm' }));
    const { user } = await rendered();

    await user.type(screen.getByLabelText(`${KEY}.design.instructionLabel`), 'A warm narrator');
    await user.click(screen.getByRole('button', { name: `${KEY}.design.submit` }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/admin/voice/fishaudio/library/designs', {
        instruction: 'A warm narrator',
        preview_text: null,
        language: null,
        count: 2,
      })
    );
    const audio = await screen.findByLabelText(`${KEY}.design.candidate`);
    expect(audio.getAttribute('src')).toBe('data:audio/wav;base64,UklGRg==');

    await user.type(screen.getByLabelText(`${KEY}.design.nameLabel`), 'Warm');
    await user.click(screen.getByRole('button', { name: `${KEY}.design.save` }));

    await waitFor(() =>
      expect(post).toHaveBeenLastCalledWith(
        `/admin/voice/fishaudio/library/designs/${'0'.repeat(32)}/save`,
        { title: 'Warm' }
      )
    );
    expect(await screen.findByText(`${KEY}.design.saved`)).toBeInTheDocument();
  });

  it('sends nothing without a description', async () => {
    const { user } = await rendered();

    await user.click(screen.getByRole('button', { name: `${KEY}.design.submit` }));

    expect(post).not.toHaveBeenCalled();
  });

  it('says the instance is paused for the day, in its own words', async () => {
    const { ApiError } = await import('@/lib/api-client');
    post.mockRejectedValue(
      new ApiError('paused', 429, { detail: { error_code: 'instance_budget_exhausted' } })
    );
    const { user } = await rendered();

    await user.type(screen.getByLabelText(`${KEY}.design.instructionLabel`), 'A warm narrator');
    await user.click(screen.getByRole('button', { name: `${KEY}.design.submit` }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(`${KEY}.errors.instance_budget_exhausted`)
    );
  });
});
