/**
 * Which side effect each `local` slash command performs.
 *
 * `conversational` commands prefill the composer and are covered by the
 * registry test; `local` ones do something to the application instead, and
 * that routing used to live as an untested `if` chain inside the chat page —
 * a component with no unit coverage and the second-worst complexity in the
 * frontend. Extracted here it is a table, and a command wired to nothing
 * fails a test instead of silently doing nothing when pressed.
 */

import { describe, it, expect, vi } from 'vitest';

import { LOCAL_COMMAND_IDS, runLocalCommand } from '../chat-local-commands';
import { STATIC_SLASH_COMMANDS } from '../slash-commands';

function handlers() {
  return { navigate: vi.fn(), openSearch: vi.fn() };
}

describe('runLocalCommand', () => {
  it('sends /briefing to the dashboard', () => {
    const h = handlers();
    runLocalCommand('briefing', h);
    expect(h.navigate).toHaveBeenCalledWith('/dashboard');
  });

  it('sends /spaces to the knowledge spaces page', () => {
    const h = handlers();
    runLocalCommand('spaces', h);
    expect(h.navigate).toHaveBeenCalledWith('/dashboard/spaces');
  });

  it('opens the history search rather than navigating', () => {
    const h = handlers();
    runLocalCommand('search', h);
    expect(h.openSearch).toHaveBeenCalledTimes(1);
    expect(h.navigate).not.toHaveBeenCalled();
  });

  it('does nothing for an id it does not own', () => {
    const h = handlers();
    runLocalCommand('agenda', h);
    expect(h.navigate).not.toHaveBeenCalled();
    expect(h.openSearch).not.toHaveBeenCalled();
  });
});

describe('the two tables agree', () => {
  // A `local` command with no handler is a menu entry that does nothing when
  // pressed — the exact failure this table exists to make impossible.
  it('handles every local command the registry declares', () => {
    const declared = STATIC_SLASH_COMMANDS.filter(c => c.kind === 'local').map(c => c.id);
    expect([...declared].sort()).toEqual([...LOCAL_COMMAND_IDS].sort());
  });

  it('never handles an id the registry does not declare', () => {
    const known = new Set(STATIC_SLASH_COMMANDS.map(c => c.id));
    for (const id of LOCAL_COMMAND_IDS) expect(known.has(id)).toBe(true);
  });
});
