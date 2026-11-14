/**
 * The status line of the private MCP configuration card.
 *
 * One rule is new (ADR-280): a confirmation that still waits for its form on an
 * instance that has closed the personal servers since cannot complete — the
 * card says so instead of inviting the reader to a form it no longer offers.
 * Everything the command says of itself is still said first: a switch flipped
 * after a save does not turn « saved » into « could not be completed ».
 */
import { describe, expect, it } from 'vitest';

import { personalMCPConfigurationMessage } from '@/lib/application-personal-mcp-configuration';
import type { ApplicationCommandStatus } from '@/types/application-commands';

const COMMAND = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';

function command(
  phase: ApplicationCommandStatus['phase'],
  outcome: Partial<NonNullable<ApplicationCommandStatus['outcome']>> = {}
): ApplicationCommandStatus {
  const expires = '2099-01-01T00:00:00.000Z';
  const interaction = { interaction_id: COMMAND, kind: 'device' as const, expires_at: expires };
  return {
    schema_version: 1,
    command_id: COMMAND,
    operation_id: 'personal_mcp.configuration',
    phase,
    expires_at: expires,
    interaction,
    outcome: {
      success: false,
      phase,
      committed: false,
      no_op: false,
      error_code: null,
      interaction,
      values: {},
      ...outcome,
    },
  };
}

describe('personalMCPConfigurationMessage', () => {
  it('invites to the form while the confirmation waits and the servers are offered', () => {
    expect(personalMCPConfigurationMessage(command('waiting'), 'idle', false, false)).toBe(
      'mcp_configuration_waiting'
    );
  });

  it('says the action cannot complete once the instance has closed the servers', () => {
    expect(personalMCPConfigurationMessage(command('waiting'), 'idle', false, true)).toBe(
      'secure_failed'
    );
  });

  it.each([
    ['a save that went through', command('waiting'), 'done', false, 'mcp_configuration_saved'],
    [
      'a committed command',
      command('committed', { committed: true }),
      'idle',
      false,
      'mcp_configuration_saved',
    ],
    ['a save in flight', command('waiting'), 'busy', false, 'secure_running'],
    ['an uncertain save', command('waiting'), 'uncertain', false, 'secure_unknown'],
    ['an expired confirmation', command('waiting'), 'idle', true, 'secure_expired'],
    ['a failed command', command('failed'), 'idle', false, 'secure_failed'],
  ] as const)(
    'lets %s speak first, closed servers or not',
    (_case, status, mode, expired, message) => {
      expect(personalMCPConfigurationMessage(status, mode, expired, true)).toBe(message);
      expect(personalMCPConfigurationMessage(status, mode, expired, false)).toBe(message);
    }
  );
});
