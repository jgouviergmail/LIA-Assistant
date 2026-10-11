import { describe, expect, it, vi } from 'vitest';
import { processSSEChunk } from '..';
import { buildHandlerContext } from './context-fixture';

const change = {
  schema_version: 1,
  command_id: '00000000-0000-4000-8000-000000000002',
  actor_id: '00000000-0000-4000-8000-000000000001',
  resources: ['profile'],
  changed_fields: ['font_size'],
  observed_at: '2026-10-06T17:00:00Z',
};

describe('application state stream', () => {
  it('accepts the complete plugin group refresh without leaking values', () => {
    const { context, dispatch } = buildHandlerContext();
    const handleApplicationStateChange = vi.fn();
    const pluginChange = { ...change, resources: ['plugins', 'skills', 'user_mcp'], changed_fields: ['plugin_to_delete'] };
    processSSEChunk({ type: 'application_state_changed', content: '', metadata: { change: pluginChange } }, { ...context, handleApplicationStateChange });
    expect(handleApplicationStateChange).toHaveBeenCalledExactlyOnceWith(pluginChange);
    expect(dispatch).not.toHaveBeenCalled();
  });
  it.each([undefined, {}])('ignores a notification without change data', metadata => {
    const { context, dispatch } = buildHandlerContext();
    const handleApplicationStateChange = vi.fn();
    processSSEChunk(
      { type: 'application_state_changed', content: '', metadata },
      { ...context, handleApplicationStateChange }
    );
    expect(handleApplicationStateChange).not.toHaveBeenCalled();
    expect(dispatch).not.toHaveBeenCalled();
  });

  it('accepts a valid notification when the resource listener is not mounted', () => {
    const { context, dispatch } = buildHandlerContext();
    expect(() => processSSEChunk(
      { type: 'application_state_changed', content: '', metadata: { change } },
      context
    )).not.toThrow();
    expect(dispatch).not.toHaveBeenCalled();
  });

  it('refreshes current values on live delivery and reconnect without changing chat input', () => {
    const { context, dispatch } = buildHandlerContext({ isReplay: true });
    const handleApplicationStateChange = vi.fn();
    processSSEChunk(
      { type: 'application_state_changed', content: '', metadata: { change } },
      { ...context, handleApplicationStateChange }
    );
    expect(handleApplicationStateChange).toHaveBeenCalledExactlyOnceWith(change);
    expect(dispatch).not.toHaveBeenCalled();
  });

  it.each([
    { ...change, actor_id: 'forged' },
    { ...change, resources: ['admin'] },
    { ...change, schema_version: 2 },
    { ...change, changed_fields: [] },
    { ...change, secret: 'planted' },
  ])('rejects malformed or unsupported metadata', invalid => {
    const { context } = buildHandlerContext();
    const handleApplicationStateChange = vi.fn();
    processSSEChunk(
      { type: 'application_state_changed', content: '', metadata: { change: invalid } },
      { ...context, handleApplicationStateChange }
    );
    expect(handleApplicationStateChange).not.toHaveBeenCalled();
  });
});
