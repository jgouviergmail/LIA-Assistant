/**
 * Slash-command registry logic (UXR Lot 8, A4) — the trigger contract (the
 * whole value IS the command token) and the diacritic-insensitive filter.
 */

import { describe, it, expect } from 'vitest';

import { filterSlashCommands, isSlashTrigger, type SlashCommand } from '../slash-commands';

const COMMANDS: SlashCommand[] = [
  {
    id: 'resume',
    kind: 'conversational',
    label: 'resume',
    description: 'd',
    insertText: '/resume',
  },
  { id: 'briefing', kind: 'local', label: 'briefing', description: 'd' },
  { id: 'search', kind: 'local', label: 'recherche', description: 'd' },
  { id: 'skill:quiz', kind: 'conversational', label: 'quiz', description: 'd', insertText: 'x' },
];

describe('isSlashTrigger', () => {
  it.each(['/', '/r', '/resume', '/skill:quiz', '/RECHERCHE', '/été'])('accepts %s', value => {
    expect(isSlashTrigger(value)).toBe(true);
  });

  it.each(['', 'hello', '/resume extra', ' /resume', 'a/b', '/two words'])(
    'rejects %s (a space or prefix makes it a normal message)',
    value => {
      expect(isSlashTrigger(value)).toBe(false);
    }
  );
});

describe('filterSlashCommands', () => {
  it('returns everything on a bare slash', () => {
    expect(filterSlashCommands(COMMANDS, '/')).toHaveLength(4);
  });

  it('matches ids and localized labels, diacritic-insensitively', () => {
    expect(filterSlashCommands(COMMANDS, '/res').map(c => c.id)).toEqual(['resume']);
    // "recherche" is the FR label of the `search` id.
    expect(filterSlashCommands(COMMANDS, '/recherché').map(c => c.id)).toEqual(['search']);
    expect(filterSlashCommands(COMMANDS, '/QUIZ').map(c => c.id)).toEqual(['skill:quiz']);
  });

  it('returns empty on no match (menu auto-closes, Enter sends normally)', () => {
    expect(filterSlashCommands(COMMANDS, '/zzz')).toEqual([]);
  });
});
