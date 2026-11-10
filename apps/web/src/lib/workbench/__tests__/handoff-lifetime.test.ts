/** Account-owned, expiring, one-time proposals never travel in a URL or browser storage. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { handOff, takeHandoff, setHandoffOwner, handoffStore } from '../handoff';
import { APPLICATION_HANDOFF_TTL_MS } from '@/lib/constants';

beforeEach(() => {
  setHandoffOwner(null);
  setHandoffOwner('owner');
});
afterEach(() => {
  setHandoffOwner(null);
  vi.useRealTimers();
});
describe('application handoff', () => {
  it('notifies an already mounted destination and is consumed exactly once', () => {
    const changed = vi.fn();
    const unsubscribe = handoffStore.subscribe(changed);
    handOff('owner', { kind: 'task', title: 'Answer Ana', notes: '' });
    const pending = handoffStore.getSnapshot();
    expect(changed).toHaveBeenCalledOnce();
    expect(handoffStore.getSnapshot()).toBe(pending);
    expect(takeHandoff('task', 'owner', pending?.id)).toMatchObject({ title: 'Answer Ana' });
    expect(takeHandoff('task', 'owner', pending?.id)).toBeNull();
    unsubscribe();
  });
  it('a different destination, owner, or stale proposal id cannot consume it', () => {
    handOff('owner', { kind: 'compose', to: 'ana@example.org' });
    expect(takeHandoff('task', 'owner')).toBeNull();
    expect(takeHandoff('compose', 'stranger')).toBeNull();
    expect(takeHandoff('compose', 'owner', 'old-id')).toBeNull();
    expect(takeHandoff('compose', 'owner')).toEqual({ kind: 'compose', to: 'ana@example.org' });
  });
  it('expires and releases the payload even when no destination mounts', () => {
    vi.useFakeTimers();
    handOff('owner', { kind: 'task', title: 'Expired', notes: 'private' });
    vi.advanceTimersByTime(APPLICATION_HANDOFF_TTL_MS);
    expect(handoffStore.getSnapshot()).toBeNull();
    expect(takeHandoff('task', 'owner')).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
  });
  it('purges on logout and A-B-A, and rejects a writer from another account', () => {
    handOff('owner', { kind: 'task', title: 'Private', notes: '' });
    setHandoffOwner('other');
    expect(handOff('owner', { kind: 'task', title: 'Late', notes: '' })).toBe(false);
    setHandoffOwner('owner');
    expect(takeHandoff('task', 'owner')).toBeNull();
    handOff('owner', { kind: 'task', title: 'Private again', notes: '' });
    setHandoffOwner(null);
    expect(handoffStore.getSnapshot()).toBeNull();
  });
  it('holds a copy and retains only the latest proposal', () => {
    const payload = { kind: 'task' as const, title: 'First', notes: '' };
    handOff('owner', payload);
    payload.title = 'Mutated';
    expect(takeHandoff('task', 'owner')?.title).toBe('First');
    handOff('owner', { kind: 'task', title: 'Second', notes: '' });
    handOff('owner', {
      kind: 'memory',
      memory: { content: 'A preference', category: 'preference' },
    });
    expect(takeHandoff('task', 'owner')).toBeNull();
    expect(takeHandoff('memory', 'owner')?.memory.category).toBe('preference');
  });
});
