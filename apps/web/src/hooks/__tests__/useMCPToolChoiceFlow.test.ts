/**
 * useMCPToolChoiceFlow — choosing when LIA asks before ONE tool (spec 2026-10-30 D6, § 6).
 *
 * Like every level, a tool's choice is previewed first: a change that makes LIA ask
 * less is listed (the API's own `questions_lost`) and written only once confirmed; one
 * that asks more is written at once. Nothing is written on a failed preview, the
 * synthesis is re-read after a write, and a second choice made while the first is
 * being checked is ignored.
 */

import { createInstance } from 'i18next';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { act, renderHook } from '@/__tests__/test-utils';
import type { MCPQuestionLoss } from '@/lib/mcp-behavior';

const { useMCPBehaviorPreview, useMCPToolChoice, previews, choices } = vi.hoisted(() => ({
  useMCPBehaviorPreview: vi.fn(),
  useMCPToolChoice: vi.fn(),
  previews: { previewServer: vi.fn(), previewStrategy: vi.fn() },
  choices: { setToolChoice: vi.fn() },
}));
vi.mock('@/hooks/useMCPServerBehavior', () => ({ useMCPBehaviorPreview, useMCPToolChoice }));
const { toast } = vi.hoisted(() => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));
vi.mock('sonner', () => ({ toast }));

import { useMCPToolChoiceFlow } from '../useMCPToolChoiceFlow';

const LOSSES: MCPQuestionLoss[] = [
  { server_id: 's1', server_name: 'Notes', tool_name: 'delete_note' },
];
// `cimode` answers every key with itself.
const keys = createInstance();
await keys.init({ lng: 'cimode' });
const onApplied = vi.fn();

function setup() {
  return renderHook(() => useMCPToolChoiceFlow('s1', 'owner', onApplied, keys.t));
}

beforeEach(() => {
  vi.clearAllMocks();
  useMCPBehaviorPreview.mockReturnValue(previews);
  useMCPToolChoice.mockReturnValue(choices);
  previews.previewServer.mockResolvedValue({ behavior: undefined, questions_lost: [] });
  choices.setToolChoice.mockResolvedValue(undefined);
});

describe('useMCPToolChoiceFlow', () => {
  it('a choice that asks more is previewed, then written at once and the synthesis re-read', async () => {
    const { result } = setup();

    await act(async () => {
      await result.current.choose('read_note', 'always');
    });

    expect(previews.previewServer).toHaveBeenCalledWith('s1', {
      tool_choices: { read_note: 'always' },
    });
    expect(choices.setToolChoice).toHaveBeenCalledWith('s1', 'read_note', 'always');
    expect(onApplied).toHaveBeenCalledTimes(1);
    expect(result.current.pending).toBeNull();
  });

  it('a choice that asks less is listed first and written only once confirmed', async () => {
    previews.previewServer.mockResolvedValue({ behavior: undefined, questions_lost: LOSSES });
    const { result } = setup();

    await act(async () => {
      await result.current.choose('delete_note', 'never');
    });
    expect(result.current.pending?.losses).toEqual(LOSSES);
    expect(choices.setToolChoice).not.toHaveBeenCalled();

    await act(async () => {
      await result.current.confirm();
    });

    expect(choices.setToolChoice).toHaveBeenCalledWith('s1', 'delete_note', 'never');
    expect(onApplied).toHaveBeenCalledTimes(1);
    expect(result.current.pending).toBeNull();
  });

  it('cancelling writes nothing', async () => {
    previews.previewServer.mockResolvedValue({ behavior: undefined, questions_lost: LOSSES });
    const { result } = setup();
    await act(async () => {
      await result.current.choose('delete_note', null);
    });

    act(() => result.current.cancel());

    expect(result.current.pending).toBeNull();
    expect(choices.setToolChoice).not.toHaveBeenCalled();
  });

  it('a failed preview writes nothing and says so', async () => {
    previews.previewServer.mockRejectedValue(new Error('down'));
    const { result } = setup();

    await act(async () => {
      await result.current.choose('delete_note', 'never');
    });

    expect(choices.setToolChoice).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith('common.error');
  });

  it('a refused write says so and re-reads nothing', async () => {
    choices.setToolChoice.mockRejectedValue(new Error('refused'));
    const { result } = setup();

    await act(async () => {
      await result.current.choose('read_note', 'always');
    });

    expect(toast.error).toHaveBeenCalledWith('common.error');
    expect(onApplied).not.toHaveBeenCalled();
    expect(result.current.busy).toBe(false);
  });

  it('a second choice made while the first is checked is ignored', async () => {
    let release!: (value: { questions_lost: MCPQuestionLoss[] }) => void;
    previews.previewServer.mockReturnValueOnce(new Promise(resolve => (release = resolve)));
    const { result } = setup();

    let first!: Promise<void>;
    act(() => {
      first = result.current.choose('read_note', 'always');
    });
    expect(result.current.busy).toBe(true);
    await act(async () => {
      await result.current.choose('delete_note', 'never');
    });
    await act(async () => {
      release({ questions_lost: [] });
      await first;
    });

    expect(previews.previewServer).toHaveBeenCalledTimes(1);
    expect(choices.setToolChoice).toHaveBeenCalledTimes(1);
  });
});
