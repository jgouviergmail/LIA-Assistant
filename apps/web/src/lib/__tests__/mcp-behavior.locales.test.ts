/**
 * Every code the MCP behaviour screens translate has a sentence in each language
 * (spec 2026-10-30).
 *
 * The API publishes closed vocabularies (a backend test holds `mcp-behavior.ts` equal
 * to them); the page turns each code into a key. Key parity across locales is checked
 * elsewhere — this test checks that the keys the CODE derives from the vocabularies
 * exist, are not empty, and keep the value each sentence must quote: a choice that
 * says what it currently gives, a dialog that names its server, a count.
 */

import { describe, expect, it } from 'vitest';

import {
  MCP_BEHAVIOR_NOTES,
  MCP_CONFIRMATION_CHOICES,
  MCP_CONFIRMATION_REASONS,
  MCP_CONFIRMATION_SOURCES,
  MCP_DRIVER_KINDS,
  MCP_DRIVERS,
  MCP_EXECUTION_MODES,
  MCP_QUESTION_FLOWS,
  MCP_TOOL_CHOICES,
} from '../mcp-behavior';

import en from '../../../locales/en/translation.json';
import fr from '../../../locales/fr/translation.json';
import de from '../../../locales/de/translation.json';
import es from '../../../locales/es/translation.json';
import it_ from '../../../locales/it/translation.json';
import zh from '../../../locales/zh/translation.json';

const LOCALES = { en, fr, de, es, it: it_, zh } as const;

const C = 'settings.mcp.confirmation';
const D = 'settings.mcp.driver';
const B = 'settings.mcp.behavior';
const L = 'settings.mcp.loosening';

/** Each key and the placeholders its sentence must keep. */
const KEYS: ReadonlyArray<readonly [string, readonly string[]]> = [
  [`${C}.strategy_legend`, []],
  [`${C}.strategy_hint`, []],
  [`${C}.server_legend`, []],
  [`${C}.current_always`, []],
  [`${C}.current_as_declared`, []],
  [`${C}.saved`, []],
  ...MCP_CONFIRMATION_CHOICES.flatMap(choice => [
    [`${C}.options.${choice}.label`, []] as const,
    [`${C}.options.${choice}.description`, choice === 'inherit' ? ['value'] : []] as const,
    [`${C}.server_options.${choice}.label`, []] as const,
    [`${C}.server_options.${choice}.description`, choice === 'inherit' ? ['value'] : []] as const,
  ]),
  [`${D}.legend`, []],
  [`${D}.hint`, []],
  ...MCP_DRIVERS.flatMap(driver => [
    [`${D}.options.${driver}.label`, []] as const,
    [`${D}.options.${driver}.description`, []] as const,
  ]),
  [`${D}.unavailable.dedicated_agents_off`, []],
  [`${D}.unavailable.mcp_app`, []],
  [`${B}.title`, []],
  [`${B}.loading`, []],
  [`${B}.action`, []],
  [`${B}.dialog_title`, ['name']],
  [`${B}.load_failed`, []],
  [`${B}.preview_failed`, []],
  [`${B}.tools_title`, []],
  [`${B}.asks`, []],
  [`${B}.not_asked`, []],
  [`${B}.asks_before_task`, []],
  [`${B}.before_task`, []],
  [`${B}.before_task_covers`, []],
  [`${B}.dedicated_unasked`, []],
  [`${B}.tool_choice.label`, ['name']],
  [`${B}.tool_choice.default_asks`, []],
  [`${B}.tool_choice.default_not_asked`, []],
  ...MCP_TOOL_CHOICES.map(choice => [`${B}.tool_choice.${choice}`, []] as const),
  [`${B}.tool_choice.suspended`, []],
  [`${B}.tool_choice.never_suspended`, []],
  [`${B}.suspended_on_card_one`, ['count']],
  [`${B}.suspended_on_card_other`, ['count']],
  [`${B}.unattended_one`, ['count']],
  [`${B}.unattended_other`, ['count']],
  [`${B}.unattended_task`, []],
  ...MCP_CONFIRMATION_SOURCES.flatMap(source => [
    [`${B}.confirmation.${source}.always`, []] as const,
    [`${B}.confirmation.${source}.as_declared`, []] as const,
  ]),
  ...MCP_BEHAVIOR_NOTES.map(note => [`${B}.notes.${note}`, []] as const),
  ...MCP_EXECUTION_MODES.map(mode => [`${B}.modes.${mode}`, []] as const),
  ...MCP_DRIVER_KINDS.map(kind => [`${B}.drivers.${kind}`, []] as const),
  ...MCP_QUESTION_FLOWS.map(flow => [`${B}.flows.${flow}`, []] as const),
  ...MCP_CONFIRMATION_REASONS.map(reason => [`${B}.reasons.${reason}`, []] as const),
  [`${L}.title`, []],
  [`${L}.body`, []],
  [`${L}.responsibility`, []],
  [`${L}.confirm`, []],
  [`${L}.more_one`, ['count']],
  [`${L}.more_other`, ['count']],
];

function lookup(catalogue: unknown, path: string): unknown {
  return path
    .split('.')
    .reduce<unknown>(
      (node, part) =>
        typeof node === 'object' && node !== null ? Reflect.get(node, part) : undefined,
      catalogue
    );
}

describe('MCP behaviour translations', () => {
  it.each(Object.keys(LOCALES) as (keyof typeof LOCALES)[])(
    '%s says every code, keeping the values its sentences quote',
    locale => {
      const missing: string[] = [];
      for (const [key, placeholders] of KEYS) {
        const value = lookup(LOCALES[locale], key);
        if (typeof value !== 'string' || value.trim() === '') {
          missing.push(key);
          continue;
        }
        for (const name of placeholders)
          if (!value.includes(`{{${name}}}`)) missing.push(`${key} {{${name}}}`);
      }
      expect(missing).toEqual([]);
    }
  );
});
