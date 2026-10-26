import { describe, expect, it } from 'vitest';
import { buildSettingsShellModel } from '@/lib/settings-shell-model';
import { SETTINGS_SEARCH_META, type SettingsSearchAvailability } from '@/lib/settings-search';
import { functionPlace, worldCatalogue, worldActions, searchWorldCatalogue } from '../functions';
import { buildStaticSlashCommands } from '@/lib/slash-commands';
import en from '../../../../locales/en/translation.json';

const ALL: SettingsSearchAvailability = {
  isSuperuser: false,
  openLoopsEnabled: true,
  habitsEnabled: true,
  peersEnabled: true,
  sandboxEgressEnabled: true,
  liveEnabled: true,
  radioEnabled: true,
  avatarEnabled: true,
  debugUserAccess: true,
};
describe('native world function inventory', () => {
  it('reuses native conversational commands without executing them or inventing a tool vocabulary', () => {
    const t = (key: string) => key;
    const actions = worldActions(t);
    const native = buildStaticSlashCommands(t).filter(command => command.kind === 'conversational');
    expect(actions.map(action => action.id)).toEqual(native.map(action => action.id));
    for (const action of actions)
      expect(action.insertText).toBe(native.find(command => command.id === action.id)?.insertText);
  });
  it('uses native localized accent-insensitive search while excluding administrator matches', () => {
    const t = (key: string) => {
      let value: unknown = en;
      for (const segment of key.split('.'))
        value = value && typeof value === 'object' ? Reflect.get(value, segment) : undefined;
      return typeof value === 'string' ? value : key;
    };
    expect(
      searchWorldCatalogue(ALL, t, t(SETTINGS_SEARCH_META.memories.titleKey)).map(
        item => item.token
      )
    ).toContain('memories');
    expect(
      searchWorldCatalogue({ ...ALL, isSuperuser: true }, t, 'admin').some(item =>
        item.token.startsWith('admin-')
      )
    ).toBe(false);
  });
  it('places every available non-administrative native function exactly once and keeps native labels', () => {
    const expected = buildSettingsShellModel(ALL)
      .flatMap(tab => tab.groups.flatMap(group => group.sections))
      .filter(item => !item.token.startsWith('admin-'));
    const actual = worldCatalogue(ALL);
    expect(actual.map(item => item.token)).toEqual(expected.map(item => item.token));
    expect(new Set(actual.map(item => item.token)).size).toBe(actual.length);
    for (const item of actual)
      expect(item.titleKey).toBe(SETTINGS_SEARCH_META[item.token].titleKey);
    expect(functionPlace('memories')).toBe('memory');
    expect(functionPlace('rag-spaces')).toBe('library');
    expect(functionPlace('language')).toBe('transverse');
  });
  it('never offers administration even to a superuser, including administrative sections outside the admin tab', () => {
    const tokens = worldCatalogue({ ...ALL, isSuperuser: true }).map(item => item.token);
    expect(tokens.some(token => token.startsWith('admin-'))).toBe(false);
    expect(functionPlace('admin-mcp-servers')).toBeNull();
  });
  it('applies native availability rather than inferring a gate from every similarly named switch', () => {
    const tokens = worldCatalogue({ ...ALL, peersEnabled: false, radioEnabled: false }).map(
      item => item.token
    );
    expect(tokens).not.toContain('peers');
    expect(tokens).not.toContain('radio');
    expect(tokens).toContain('memories');
    expect(tokens).toContain('interests');
  });
});
