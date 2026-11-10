/**
 * What one tool hands to another (ADR-369, lot 2): held in the page, never in an
 * address a server would log; taken once, by the tool it was meant for.
 */
import { beforeEach, afterEach, describe, expect, it } from 'vitest';

import { handOff, takeHandoff, setHandoffOwner } from '../handoff';

afterEach(() => {
  takeHandoff('task', 'owner');
  takeHandoff('compose', 'owner');
});

describe('takeHandoff', () => {
  it('gives what was handed, once', () => {
    handOff('owner', { kind: 'task', title: 'Answer Ana', notes: '' });

    expect(takeHandoff('task', 'owner')).toEqual({ kind: 'task', title: 'Answer Ana', notes: '' });
    expect(takeHandoff('task', 'owner')).toBeNull();
  });

  it('leaves what another tool was handed', () => {
    handOff('owner', { kind: 'compose', to: 'ana@example.org' });

    expect(takeHandoff('task', 'owner')).toBeNull();
    expect(takeHandoff('compose', 'owner')).toEqual({ kind: 'compose', to: 'ana@example.org' });
  });

  it('keeps the last thing handed', () => {
    handOff('owner', { kind: 'task', title: 'First', notes: '' });
    handOff('owner', { kind: 'task', title: 'Second', notes: '' });

    expect(takeHandoff('task', 'owner')).toMatchObject({ title: 'Second' });
  });
});

beforeEach(() => {
  setHandoffOwner(null);
  setHandoffOwner('owner');
});
