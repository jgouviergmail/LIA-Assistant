/**
 * useMCPServerFormBehavior — the server form's choices (spec 2026-10-30 D3, D4, D6).
 *
 * What the form would change is what differs from the stored row: the preview judges
 * exactly that, and the save writes exactly that. The ReAct shape is written only when
 * the final driver differs from where it started — a driver brought back writes
 * nothing, so an untouched shape stays NULL and keeps following the instance default.
 */

import { describe, expect, it } from 'vitest';

import { act, renderHook } from '@/__tests__/test-utils';
import type { UserMCPDefaults } from '@/lib/mcp-behavior';

import { useMCPServerFormBehavior, type MCPStoredBehavior } from '../useMCPServerFormBehavior';

const DEFAULTS: UserMCPDefaults = {
  confirmation_instance: false,
  confirmation_account: true,
  confirmation_effective: true,
  react_direct_tools_default: true,
  dedicated_agents_available: true,
};

const ITERATIVE: MCPStoredBehavior = {
  hitl_required: null,
  iterative_mode: true,
  react_expand_iterative: null,
};

function setup(stored: MCPStoredBehavior | null = ITERATIVE) {
  return renderHook(() => useMCPServerFormBehavior(stored, DEFAULTS));
}

describe('useMCPServerFormBehavior', () => {
  it('starts from the stored row and changes nothing', () => {
    const { result } = setup();

    expect(result.current.confirmation).toBe('inherit');
    expect(result.current.driver).toBe('pipeline_agent');
    expect(result.current.candidates).toEqual({});
  });

  it('a new server starts on « like my strategy », driven directly', () => {
    const { result } = setup(null);

    expect(result.current.confirmation).toBe('inherit');
    expect(result.current.driver).toBe('direct');
  });

  it('a confirmation change is a candidate and a write', () => {
    const { result } = setup();

    act(() => result.current.setConfirmation('as_declared'));

    expect(result.current.candidates).toEqual({ hitl_required: false });
  });

  it('a driver change writes the shape it implies', () => {
    const { result } = setup();

    act(() => result.current.setDriver('agent_everywhere'));

    expect(result.current.candidates).toEqual({ react_expand_iterative: false });
  });

  it('from direct, a dedicated agent is both a mode and a shape', () => {
    const { result } = setup({ ...ITERATIVE, iterative_mode: false });

    act(() => result.current.setDriver('pipeline_agent'));

    expect(result.current.candidates).toEqual({
      iterative_mode: true,
      react_expand_iterative: true,
    });
  });

  it('a driver brought back to where it started writes nothing', () => {
    const { result } = setup();

    act(() => result.current.setDriver('agent_everywhere'));
    act(() => result.current.setDriver('pipeline_agent'));

    expect(result.current.candidates).toEqual({});
  });

  it('keeps the same candidates object until a choice changes', () => {
    // The live synthesis keys its preview on it: a new object per render must not
    // read as a new change.
    const { result, rerender } = setup();
    act(() => result.current.setConfirmation('always'));
    const first = result.current.candidates;

    rerender();

    expect(result.current.candidates).toBe(first);
  });

  it('reset starts again from another row', () => {
    const { result } = setup();

    act(() => result.current.setConfirmation('always'));
    act(() => result.current.reset({ ...ITERATIVE, hitl_required: false }));

    expect(result.current.confirmation).toBe('as_declared');
    expect(result.current.candidates).toEqual({});
  });

  it('a tool’s choice is a candidate like the others, the last one kept', () => {
    const { result } = setup();

    act(() => result.current.setToolChoice('delete_note', 'never'));
    act(() => result.current.setToolChoice('read_note', 'always'));
    act(() => result.current.setToolChoice('delete_note', null));

    expect(result.current.candidates).toEqual({
      tool_choices: { delete_note: null, read_note: 'always' },
    });
  });

  it('reset forgets the tools’ choices made in the form', () => {
    const { result } = setup();

    act(() => result.current.setToolChoice('delete_note', 'never'));
    act(() => result.current.reset(ITERATIVE));

    expect(result.current.candidates).toEqual({});
  });
});
