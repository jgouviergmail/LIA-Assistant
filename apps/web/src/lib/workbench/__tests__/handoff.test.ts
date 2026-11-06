/**
 * What one tool hands to another (ADR-369, lot 2): held in the page, never in an
 * address a server would log; taken once, by the tool it was meant for.
 */
import { afterEach, describe, expect, it } from 'vitest';

import { handOff, takeHandoff } from '../handoff';

afterEach(() => {
  takeHandoff('task');
  takeHandoff('compose');
});

describe('takeHandoff', () => {
  it('gives what was handed, once', () => {
    handOff({ kind: 'task', title: 'Answer Ana', notes: '' });

    expect(takeHandoff('task')).toEqual({ kind: 'task', title: 'Answer Ana', notes: '' });
    expect(takeHandoff('task')).toBeNull();
  });

  it('leaves what another tool was handed', () => {
    handOff({ kind: 'compose', to: 'ana@example.org' });

    expect(takeHandoff('task')).toBeNull();
    expect(takeHandoff('compose')).toEqual({ kind: 'compose', to: 'ana@example.org' });
  });

  it('keeps the last thing handed', () => {
    handOff({ kind: 'task', title: 'First', notes: '' });
    handOff({ kind: 'task', title: 'Second', notes: '' });

    expect(takeHandoff('task')).toMatchObject({ title: 'Second' });
  });
});
