/**
 * The alerts hub offers the sections this instance serves NOW.
 *
 * Its tickets read the workboard's deployment ceiling: an operator who had
 * switched the board off still saw the section, over routes that refuse.
 */
import { describe, expect, it } from 'vitest';

import { appConfigFixture } from '@/__tests__/fixtures/app-config';
import { alertCategoryAvailability } from '@/lib/alert-categories';

const MOUNTED = appConfigFixture({ features: { workboard_enabled: true } });

describe('alertCategoryAvailability', () => {
  it('offers the tickets where the deployment mounts the board', () => {
    expect(alertCategoryAvailability(MOUNTED).workboard).toBe(true);
    expect(alertCategoryAvailability(appConfigFixture()).workboard).toBe(false);
  });

  it('withdraws the tickets once the operator switched the board off', () => {
    const off = { ...MOUNTED, capabilities: { workboard: { enabled: false, family: 'work' } } };

    expect(alertCategoryAvailability(off).workboard).toBe(false);
  });

  it('withdraws the peer messages with the connections: their router refuses', () => {
    const mounted = appConfigFixture({ features: { peers_enabled: true } });
    const off = { ...mounted, capabilities: { peers: { enabled: false, family: 'people' } } };

    expect(alertCategoryAvailability(mounted).peer_messages).toBe(true);
    expect(alertCategoryAvailability(off).peer_messages).toBe(false);
  });

  it('keeps the proactive history: what was sent is a record, readable under the flag', () => {
    const mounted = appConfigFixture({ features: { heartbeat_enabled: true } });
    const off = { ...mounted, capabilities: { heartbeat: { enabled: false, family: 'work' } } };

    expect(alertCategoryAvailability(off).proactive).toBe(true);
    expect(alertCategoryAvailability(appConfigFixture()).proactive).toBe(false);
  });

  it('offers nothing gated before the configuration answers', () => {
    expect(alertCategoryAvailability(null).workboard).toBe(false);
    expect(alertCategoryAvailability(undefined).workboard).toBe(false);
  });
});
