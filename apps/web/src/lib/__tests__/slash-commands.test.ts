/**
 * Slash-command registry logic (UXR Lot 8, A4) — the trigger contract (the
 * whole value IS the command token) and the diacritic-insensitive filter.
 */

import { describe, it, expect } from 'vitest';

import {
  buildStaticSlashCommands,
  filterSlashCommands,
  isSlashTrigger,
  STATIC_SLASH_COMMAND_IDS,
  STATIC_SLASH_COMMANDS,
  userShortcutCommands,
  type SlashCommand,
} from '../slash-commands';

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

describe('static command table (SLASH admin lot)', () => {
  it('localizes every entry and keeps /resume a literal insert', () => {
    const t = (key: string) => `T(${key})`;
    const commands = buildStaticSlashCommands(t);

    expect(commands.map(c => c.id)).toEqual(STATIC_SLASH_COMMANDS.map(d => d.id));
    const resume = commands.find(c => c.id === 'resume');
    // The backend compaction node consumes the LITERAL token, never a translation.
    expect(resume?.insertText).toBe('/resume');
    const agenda = commands.find(c => c.id === 'agenda');
    expect(agenda?.insertText).toBe('T(chat.slash.agenda_intent)');
    // Local commands insert nothing — the page owns their handlers.
    expect(commands.find(c => c.id === 'briefing')?.insertText).toBeUndefined();
  });

  it('exposes the exact reserved-id set the settings form refuses', () => {
    expect(STATIC_SLASH_COMMAND_IDS).toEqual(new Set(STATIC_SLASH_COMMANDS.map(d => d.id)));
    expect(STATIC_SLASH_COMMAND_IDS.has('resume')).toBe(true);
  });

  // The rail covered "what do I have" (agenda, emails, tasks, reminders) but
  // none of the everyday CREATIONS, nor the door to the knowledge spaces.
  it.each([
    ['new-reminder', 'conversational'],
    ['new-routine', 'conversational'],
    ['spaces', 'local'],
  ])('offers /%s as a %s command', (id, kind) => {
    const entry = STATIC_SLASH_COMMANDS.find(d => d.id === id);
    expect(entry).toBeDefined();
    expect(entry?.kind).toBe(kind);
  });

  it('prefills the creations and navigates for the spaces door', () => {
    const t = (key: string) => `T(${key})`;
    const commands = buildStaticSlashCommands(t);

    expect(commands.find(c => c.id === 'new-reminder')?.insertText).toBe(
      'T(chat.slash.new_reminder_intent)'
    );
    expect(commands.find(c => c.id === 'new-routine')?.insertText).toBe(
      'T(chat.slash.new_routine_intent)'
    );
    // A navigation inserts nothing — the page owns the handler.
    expect(commands.find(c => c.id === 'spaces')?.insertText).toBeUndefined();
  });

  it('keeps the creation ids distinct from the listing ones', () => {
    // `/reminders` lists, `/new-reminder` creates: two different requests, and
    // an id collision would make one unreachable.
    expect(STATIC_SLASH_COMMAND_IDS.has('reminders')).toBe(true);
    expect(STATIC_SLASH_COMMAND_IDS.has('new-reminder')).toBe(true);
  });

  it('declares no duplicate id at all', () => {
    const ids = STATIC_SLASH_COMMANDS.map(d => d.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});

describe('userShortcutCommands', () => {
  it('maps a shortcut to a prefilling conversational command', () => {
    const [command] = userShortcutCommands([{ id: 'meteo-eze', text: 'Météo à Èze ?' }]);
    expect(command).toEqual({
      id: 'meteo-eze',
      kind: 'conversational',
      label: 'meteo-eze',
      description: 'Météo à Èze ?',
      insertText: 'Météo à Èze ?',
    });
  });

  it('drops legacy shortcuts colliding with a static id — statics win', () => {
    const commands = userShortcutCommands([
      { id: 'weather', text: 'shadowing attempt' },
      { id: 'mine', text: 'kept' },
    ]);
    expect(commands.map(c => c.id)).toEqual(['mine']);
  });
});
