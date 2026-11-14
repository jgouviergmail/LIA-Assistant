/**
 * MemorySettings — the memories manager: loading, the category sections that
 * stay collapsed until opened, pinning (whose confirmation wording follows the
 * previous state), and above all the **asymmetric deletion rule** — an ordinary
 * memory is deleted on the spot, a *pinned* one must be confirmed first. The
 * bulk deletion likewise distinguishes "wipe everything" from "keep the pinned
 * ones", with its own wording.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { act, fireEvent, renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { handOff, setHandoffOwner, handoffStore } from '@/lib/workbench/handoff';
import { makeUser } from '@/__tests__/factories';

const { useMemories } = vi.hoisted(() => ({ useMemories: vi.fn() }));
// The module also exports helpers the component renders with (getEmotionalEmoji);
// keep the real exports and swap only the hook.
vi.mock('@/hooks/useMemories', async importOriginal => {
  const actual = await importOriginal<typeof import('@/hooks/useMemories')>();
  return { ...actual, useMemories };
});
const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
const { patch } = vi.hoisted(() => ({ patch: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { patch } }));
const { toast } = vi.hoisted(() => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));
vi.mock('sonner', () => ({ toast }));

import { MemorySettings } from '../MemorySettings';
import type { Memory, MemoryLimits, useMemories as useMemoriesFn } from '@/hooks/useMemories';

type MemoriesHook = ReturnType<typeof useMemoriesFn>;

/** What the API publishes on the list: the form holds a text to these. */
const LIMITS: MemoryLimits = {
  content_min_chars: 3,
  content_max_chars: 500,
  trigger_topic_max_chars: 100,
  usage_nuance_max_chars: 300,
  import_max_memories: 500,
  import_max_file_kb: 64,
};

function memory(over: Partial<Memory> = {}): Memory {
  return {
    id: 'm1',
    content: 'Prefers concise answers',
    category: 'preference',
    emotional_weight: 0.4,
    trigger_topic: 'style',
    usage_nuance: 'when answering',
    importance: 3,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    pinned: false,
    ...over,
  };
}

function hook(over: Partial<MemoriesHook> = {}) {
  return {
    memories: [memory()],
    total: 1,
    limits: LIMITS,
    loading: false,
    creating: false,
    deleting: false,
    updating: false,
    deletingAll: false,
    createMemory: vi.fn(),
    deleteMemory: vi.fn(),
    updateMemory: vi.fn(),
    deleteAllMemories: vi.fn(),
    togglePin: vi.fn(),
    importing: false,
    importMemories: vi.fn(),
    ...over,
  };
}

function render() {
  return renderWithProviders(<MemorySettings lng="en" />);
}

/** Memories live in collapsed per-category sections. */
async function openCategory(user: ReturnType<typeof render>['user']) {
  await user.click(await screen.findByRole('button', { name: /preference/i }));
}

const DELETE = 'memories.delete';
const PIN = 'memories.pin';
const UNPIN = 'memories.unpin';

beforeEach(() => {
  setHandoffOwner(null);
  setHandoffOwner('owner');
  vi.clearAllMocks();
  patch.mockResolvedValue({});
  useAuth.mockReturnValue({
    user: makeUser({ id: 'owner', memory_enabled: true }),
    refreshUser: vi.fn(),
  });
  useMemories.mockReturnValue(hook());
});
afterEach(() => setHandoffOwner(null));

describe('MemorySettings — AI proposal in the native create form', () => {
  it('claims one save, retains the proposal on refusal, and rejects a result arriving after an account change', async () => {
    let settle: (value: Memory) => void = () => undefined;
    const createMemory = vi
      .fn<MemoriesHook['createMemory']>()
      .mockRejectedValueOnce(new Error('offline'))
      .mockImplementation(
        () =>
          new Promise(resolve => {
            settle = resolve;
          })
      );
    useMemories.mockReturnValue(hook({ createMemory }));
    const view = render();
    act(() => {
      handOff('owner', {
        kind: 'memory',
        memory: { content: 'Private proposal', category: 'preference' },
      });
    });
    await screen.findByLabelText('memories.field_content *');
    await view.user.click(screen.getByRole('button', { name: 'memories.create_button' }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('memories.create_error'));
    expect(screen.getByLabelText('memories.field_content *')).toHaveValue('Private proposal');
    const button = screen.getByRole('button', { name: 'memories.create_button' });
    act(() => {
      fireEvent.click(button);
      fireEvent.click(button);
    });
    expect(createMemory).toHaveBeenCalledTimes(2);
    useAuth.mockReturnValue({
      user: makeUser({ id: 'another', memory_enabled: true }),
      refreshUser: vi.fn(),
    });
    act(() => setHandoffOwner('another'));
    view.rerender(<MemorySettings lng="en" />);
    await act(async () => settle(memory()));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(toast.success).not.toHaveBeenCalled();
  });
  it('receives a proposal while already open, permits editing, and saves only on the person’s click', async () => {
    const createMemory = vi.fn().mockResolvedValue(memory());
    useMemories.mockReturnValue(hook({ createMemory }));
    const { user } = render();
    act(() => {
      handOff('owner', {
        kind: 'memory',
        memory: {
          content: 'Prefers green tea',
          category: 'preference',
          usage_nuance: 'At breakfast',
          importance: 0.6,
        },
      });
    });
    const field = await screen.findByLabelText('memories.field_content *');
    expect(field).toHaveValue('Prefers green tea');
    expect(screen.getByLabelText('memories.field_usage_nuance')).toHaveValue('At breakfast');
    expect(createMemory).not.toHaveBeenCalled();
    await user.clear(field);
    await user.type(field, 'Prefers jasmine tea');
    await user.click(screen.getByRole('button', { name: 'memories.create_button' }));
    await waitFor(() =>
      expect(createMemory).toHaveBeenCalledWith(
        expect.objectContaining({
          content: 'Prefers jasmine tea',
          category: 'preference',
          importance: 0.6,
        })
      )
    );
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(toast.error).not.toHaveBeenCalled();
  });
  it('keeps a dirty form intact and presents a waiting proposal after cancellation', async () => {
    const { user } = render();
    await user.click(screen.getByRole('button', { name: 'memories.create' }));
    const field = await screen.findByLabelText('memories.field_content *');
    await user.type(field, 'My own unfinished memory');
    act(() => {
      handOff('owner', {
        kind: 'memory',
        memory: { content: 'New proposal', category: 'personal' },
      });
    });
    expect(field).toHaveValue('My own unfinished memory');
    expect(handoffStore.getSnapshot()).not.toBeNull();
    await user.click(screen.getByRole('button', { name: 'common.cancel' }));
    await waitFor(() =>
      expect(screen.getByLabelText('memories.field_content *')).toHaveValue('New proposal')
    );
  });
});

describe('MemorySettings — list', () => {
  it('shows a loading spinner while memories load', () => {
    useMemories.mockReturnValue(hook({ loading: true, memories: [] }));
    render();
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('keeps a category collapsed until it is opened', async () => {
    const { user } = render();
    expect(screen.queryByText('Prefers concise answers')).not.toBeInTheDocument();
    await openCategory(user);
    expect(await screen.findByText('Prefers concise answers')).toBeInTheDocument();
  });
});

describe('MemorySettings — pinning', () => {
  it('pins an unpinned memory and confirms accordingly', async () => {
    const togglePin = vi.fn().mockResolvedValue(undefined);
    useMemories.mockReturnValue(hook({ memories: [memory({ pinned: false })], togglePin }));
    const { user } = render();
    await openCategory(user);
    await user.click(await screen.findByRole('button', { name: PIN }));
    await waitFor(() => expect(togglePin).toHaveBeenCalledWith('m1', true));
    expect(toast.success).toHaveBeenCalledWith('memories.pin_success');
  });

  it('unpins a pinned memory with the opposite wording', async () => {
    const togglePin = vi.fn().mockResolvedValue(undefined);
    useMemories.mockReturnValue(hook({ memories: [memory({ pinned: true })], togglePin }));
    const { user } = render();
    await openCategory(user);
    await user.click(await screen.findByRole('button', { name: UNPIN }));
    await waitFor(() => expect(togglePin).toHaveBeenCalledWith('m1', false));
    expect(toast.success).toHaveBeenCalledWith('memories.unpin_success');
  });

  it('reports a failed pin toggle', async () => {
    useMemories.mockReturnValue(
      hook({ memories: [memory()], togglePin: vi.fn().mockRejectedValue(new Error('boom')) })
    );
    const { user } = render();
    await openCategory(user);
    await user.click(await screen.findByRole('button', { name: PIN }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('memories.pin_error'));
  });
});

describe('MemorySettings — asymmetric deletion', () => {
  it('deletes an ordinary memory on the spot', async () => {
    const deleteMemory = vi.fn().mockResolvedValue(undefined);
    useMemories.mockReturnValue(hook({ memories: [memory({ pinned: false })], deleteMemory }));
    const { user } = render();
    await openCategory(user);
    await user.click(await screen.findByRole('button', { name: DELETE }));
    await waitFor(() => expect(deleteMemory).toHaveBeenCalledWith('m1'));
    expect(toast.success).toHaveBeenCalledWith('memories.delete_success');
  });

  it('never deletes a pinned memory without a confirmation', async () => {
    const deleteMemory = vi.fn().mockResolvedValue(undefined);
    useMemories.mockReturnValue(hook({ memories: [memory({ pinned: true })], deleteMemory }));
    const { user } = render();
    await openCategory(user);
    await user.click(await screen.findByRole('button', { name: DELETE }));
    // The click only arms the confirmation — nothing is destroyed yet.
    expect(deleteMemory).not.toHaveBeenCalled();
  });

  it('reports a failed deletion', async () => {
    useMemories.mockReturnValue(
      hook({
        memories: [memory({ pinned: false })],
        deleteMemory: vi.fn().mockRejectedValue(new Error('boom')),
      })
    );
    const { user } = render();
    await openCategory(user);
    await user.click(await screen.findByRole('button', { name: DELETE }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('memories.delete_error'));
  });
});

describe('MemorySettings — memory switch', () => {
  it('persists the memory preference and refreshes the user', async () => {
    const ctx = { user: makeUser({ memory_enabled: true }), refreshUser: vi.fn() };
    useAuth.mockReturnValue(ctx);
    const { user } = render();
    await user.click(screen.getByRole('switch'));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/auth/me/memory-preference', { memory_enabled: false })
    );
    expect(ctx.refreshUser).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledWith('memories.disabled_success');
  });

  it('reports a failed preference change', async () => {
    patch.mockRejectedValue(new Error('boom'));
    const { user } = render();
    await user.click(screen.getByRole('switch'));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('common.error'));
  });
});

/**
 * Export stays a VISIBLE button at every size (owner request 2026-08-05):
 * folded into the phone "⋯" menu it read as absent. With export pinned and
 * nothing else foldable, the "⋯" trigger must not render at all.
 */
describe('MemorySettings — pinned export', () => {
  it('keeps Export inline with no size gating and no "⋯" menu', async () => {
    render();
    const exportBtn = await screen.findByRole('button', { name: 'memories.export' });
    expect(exportBtn.closest('.hidden')).toBeNull();
    expect(screen.queryByRole('button', { name: 'common.more_actions' })).toBeNull();
  });
});

describe('MemorySettings — importing an export', () => {
  const exported = () => new File(['content,category\nA fact,personal\n'], 'memories.csv');
  const picker = () => screen.findByLabelText('memories.import_file');

  it('offers Import beside Export, at every size, even with no memory yet', async () => {
    useMemories.mockReturnValue(hook({ memories: [], total: 0 }));
    render();

    const action = await screen.findByRole('button', { name: 'memories.import' });
    expect(action.closest('.hidden')).toBeNull();
    expect(action).toBeEnabled();
  });

  it('sends the picked export and says what became of every entry', async () => {
    const importMemories = vi.fn<MemoriesHook['importMemories']>().mockResolvedValue({
      total: 3,
      imported: 2,
      already_present: 1,
      duplicates: 0,
      invalid: 0,
    });
    useMemories.mockReturnValue(hook({ importMemories }));
    const { user } = render();
    const file = exported();

    await user.upload(await picker(), file);

    await waitFor(() => expect(importMemories).toHaveBeenCalledWith(file));
    expect(toast.success).toHaveBeenCalledWith(
      'memories.import_imported · memories.import_already_present'
    );
    // The same file picked again is a new choice, not no change.
    expect(await picker()).toHaveValue('');
  });

  it('does not call a file that brought nothing new a success', async () => {
    const importMemories = vi.fn<MemoriesHook['importMemories']>().mockResolvedValue({
      total: 2,
      imported: 0,
      already_present: 2,
      duplicates: 0,
      invalid: 0,
    });
    useMemories.mockReturnValue(hook({ importMemories }));
    const { user } = render();

    await user.upload(await picker(), exported());

    await waitFor(() =>
      expect(toast.info).toHaveBeenCalledWith(
        'memories.import_imported · memories.import_already_present'
      )
    );
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('says why the API refused the file, in the API’s own words', async () => {
    const importMemories = vi
      .fn<MemoriesHook['importMemories']>()
      .mockRejectedValue(new Error('This file is not a LIA memories export (CSV or JSON)'));
    useMemories.mockReturnValue(hook({ importMemories }));
    const { user } = render();

    await user.upload(await picker(), exported());

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        'This file is not a LIA memories export (CSV or JSON)'
      )
    );
  });

  it('does not send a file larger than the import reads: the bound is published', async () => {
    const importMemories = vi.fn<MemoriesHook['importMemories']>();
    useMemories.mockReturnValue(hook({ importMemories }));
    const { user } = render();
    const oversized = exported();
    Object.defineProperty(oversized, 'size', { value: 64 * 1024 + 1 });

    await user.upload(await picker(), oversized);

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('memories.import_too_large'));
    expect(importMemories).not.toHaveBeenCalled();
  });

  it('opens the file picker from the action', async () => {
    const { user } = render();
    const opened = vi.spyOn(await picker(), 'click');

    await user.click(await screen.findByRole('button', { name: 'memories.import' }));

    expect(opened).toHaveBeenCalledTimes(1);
  });

  it('holds the action while an import runs, without dropping it from the page', async () => {
    useMemories.mockReturnValue(hook({ importing: true }));
    const { user } = render();
    const opened = vi.spyOn(await picker(), 'click');

    const action = await screen.findByRole('button', { name: 'memories.import' });
    // Busy, never natively disabled: a control disabled while it holds the
    // focus drops the keyboard user who just activated it back on the page top.
    expect(action).toHaveAttribute('aria-busy', 'true');
    expect(action).toBeEnabled();
    // The guard, not the attribute, is what refuses a second file meanwhile.
    await user.click(action);
    expect(opened).not.toHaveBeenCalled();
  });
});

describe('MemorySettings — the form says what the API would refuse', () => {
  // Measured in production on 2026-11-06: a 495-character memory, a few words added,
  // and five saves answered the same bare error, while the API refused the text for
  // its length. The person tried unpinning it, a reason the screen never gave.
  const SAVE = 'common.save';
  const CONTENT = 'memories.field_content';

  async function openEdit(user: ReturnType<typeof render>['user']) {
    await openCategory(user);
    await user.click(await screen.findByRole('button', { name: 'memories.edit' }));
    return screen.findByLabelText(CONTENT);
  }

  it('says why, and holds Save, the moment a memory outgrows its bound', async () => {
    const updateMemory = vi.fn();
    useMemories.mockReturnValue(
      hook({ memories: [memory({ content: 'x'.repeat(495) })], updateMemory })
    );
    const { user } = render();
    const field = await openEdit(user);

    await user.type(field, 'plus !');

    expect(await screen.findByRole('alert')).toHaveTextContent('memories.text_too_long');
    expect(field).toHaveAttribute('aria-invalid', 'true');
    const save = screen.getByRole('button', { name: SAVE });
    expect(save).toBeDisabled();
    await user.click(save);
    expect(updateMemory).not.toHaveBeenCalled();
  });

  it('saves again once the text is back within its bound', async () => {
    const updateMemory = vi.fn().mockResolvedValue(undefined);
    useMemories.mockReturnValue(
      hook({ memories: [memory({ content: 'x'.repeat(495) })], updateMemory })
    );
    const { user } = render();
    const field = await openEdit(user);

    await user.type(field, 'plus !{Backspace}');

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: SAVE }));
    await waitFor(() =>
      expect(updateMemory).toHaveBeenCalledWith(
        'm1',
        expect.objectContaining({ content: `${'x'.repeat(495)}plus ` })
      )
    );
    expect(toast.success).toHaveBeenCalledWith('memories.update_success');
  });

  it.each([
    ['a text the API refused', 422, 'memories.text_refused'],
    ['any other failure', 500, 'memories.update_error'],
  ])('says so for %s', async (_case, status, expected) => {
    const updateMemory = vi.fn().mockRejectedValue(Object.assign(new Error('refused'), { status }));
    useMemories.mockReturnValue(hook({ updateMemory }));
    const { user } = render();
    await openEdit(user);

    await user.click(screen.getByRole('button', { name: SAVE }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(expected));
  });

  it('counts an emoji once, as the API does', async () => {
    useMemories.mockReturnValue(hook({ memories: [memory({ content: '😀'.repeat(500) })] }));
    const { user } = render();
    await openEdit(user);

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: SAVE })).toBeEnabled();
  });

  it('attaches the count to the field, for whoever cannot see it', async () => {
    const { user } = render();
    const field = await openEdit(user);

    expect(field).toHaveAccessibleDescription('memories.characters');
  });

  it.each([
    ['memories.field_trigger_topic', LIMITS.trigger_topic_max_chars],
    ['memories.field_usage_nuance', LIMITS.usage_nuance_max_chars],
  ])('holds %s to its own bound', async (label, ceiling) => {
    const { user } = render();
    await openEdit(user);

    fireEvent.change(screen.getByLabelText(label), { target: { value: 'x'.repeat(ceiling) } });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: SAVE })).toBeEnabled();

    fireEvent.change(screen.getByLabelText(label), {
      target: { value: 'x'.repeat(ceiling + 1) },
    });
    expect(await screen.findByRole('alert')).toHaveTextContent('memories.text_too_long');
    expect(screen.getByRole('button', { name: SAVE })).toBeDisabled();
  });

  it('clears a nuance and a trigger for real: an emptied field reaches the API', async () => {
    const updateMemory = vi.fn().mockResolvedValue(undefined);
    useMemories.mockReturnValue(hook({ updateMemory }));
    const { user } = render();
    await openEdit(user);

    await user.clear(screen.getByLabelText('memories.field_usage_nuance'));
    await user.clear(screen.getByLabelText('memories.field_trigger_topic'));
    await user.click(screen.getByRole('button', { name: SAVE }));

    await waitFor(() =>
      expect(updateMemory).toHaveBeenCalledWith(
        'm1',
        expect.objectContaining({ usage_nuance: '', trigger_topic: '' })
      )
    );
  });

  it('keeps working before the limits are known: the API still decides', async () => {
    useMemories.mockReturnValue(hook({ limits: undefined }));
    const { user } = render();
    const field = await openEdit(user);

    expect(field).not.toHaveAccessibleDescription();
    expect(screen.getByRole('button', { name: SAVE })).toBeEnabled();
  });

  describe('the create dialog', () => {
    const CREATE = 'memories.create_button';

    async function openCreate(user: ReturnType<typeof render>['user']) {
      await user.click(await screen.findByRole('button', { name: 'memories.create' }));
      return screen.findByLabelText(`${CONTENT} *`);
    }

    it('does not scold a form nobody has filled yet', async () => {
      const { user } = render();
      await openCreate(user);

      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: CREATE })).toBeDisabled();
    });

    it('states the floor as soon as a too-short text is typed', async () => {
      const { user } = render();
      const field = await openCreate(user);

      await user.type(field, 'ab');
      expect(await screen.findByRole('alert')).toHaveTextContent('memories.text_too_short');
      expect(screen.getByRole('button', { name: CREATE })).toBeDisabled();

      await user.type(field, 'c');
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: CREATE })).toBeEnabled();
    });

    it('names a text the API refused, with the limits still unknown', async () => {
      const createMemory = vi
        .fn()
        .mockRejectedValue(Object.assign(new Error('refused'), { status: 422 }));
      useMemories.mockReturnValue(hook({ limits: undefined, createMemory }));
      const { user } = render();
      const field = await openCreate(user);

      await user.type(field, 'abc');
      await user.click(screen.getByRole('button', { name: CREATE }));

      await waitFor(() => expect(toast.error).toHaveBeenCalledWith('memories.text_refused'));
    });

    it('holds a new memory to the same ceiling', async () => {
      const { user } = render();
      const field = await openCreate(user);

      fireEvent.change(field, { target: { value: 'x'.repeat(LIMITS.content_max_chars + 1) } });

      expect(await screen.findByRole('alert')).toHaveTextContent('memories.text_too_long');
      expect(screen.getByRole('button', { name: CREATE })).toBeDisabled();
    });
  });
});

describe('procedural category (ADR-236) — the learned-rules admin surface', () => {
  it('every category of the type is offered by the edit selector', async () => {
    const { MEMORY_CATEGORIES } = await import('@/hooks/useMemories');

    // The single source the selectors must render from — `procedural`
    // missing here is how learned rules became invisible to their owner.
    expect(MEMORY_CATEGORIES).toContain('procedural');
    // Icons stay complete by type, but assert the runtime map too.
    const { CATEGORY_ICONS } = await import('../MemoryFormFields');
    for (const category of MEMORY_CATEGORIES) {
      expect(CATEGORY_ICONS[category], `icon for ${category}`).toBeTruthy();
    }
  });
});

describe('category labels exist in the REAL locales', () => {
  // The i18n mock echoes keys, so a label landing under the wrong JSON
  // parent is invisible to every component test — the user saw
  // `memories.categories.procedural` raw on screen (2026-08-20). This
  // loads the actual locale files: every category of the type must have
  // its translation at the exact path getCategoryLabel reads.
  it.each(['en', 'fr', 'de', 'es', 'it', 'zh'])('%s covers every category', async lng => {
    const { MEMORY_CATEGORIES } = await import('@/hooks/useMemories');
    const translation = (await import(`../../../../locales/${lng}/translation.json`)).default;

    for (const category of MEMORY_CATEGORIES) {
      expect(
        translation.memories?.categories?.[category],
        `${lng}: memories.categories.${category}`
      ).toBeTruthy();
    }
  });

  // The stub echoes keys, so only the real files can say a refusal carries its figures:
  // without its placeholder, the reason reads as a bare sentence with no number in it.
  it.each(['en', 'fr', 'de', 'es', 'it', 'zh'])('%s words every refusal', async lng => {
    const translation = (await import(`../../../../locales/${lng}/translation.json`)).default;
    const { memories } = translation;

    expect(memories.characters, `${lng}: characters`).toContain('{{count}}');
    expect(memories.characters, `${lng}: characters`).toContain('{{max}}');
    expect(memories.text_too_long, `${lng}: too long`).toContain('{{max}}');
    // An alert is announced again whenever its text changes: no moving figure here.
    expect(memories.text_too_long, `${lng}: too long`).not.toContain('{{count}}');
    expect(memories.text_too_short, `${lng}: too short`).toContain('{{min}}');
    expect(memories.text_refused, `${lng}: refused`).toBeTruthy();
  });
});
