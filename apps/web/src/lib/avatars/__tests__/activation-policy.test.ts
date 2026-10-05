import { expect, it } from 'vitest';
import { avatarDemand, sameAvatar } from '../activation-policy';
import type { AvatarConfig } from '../types';

const config: AvatarConfig = {
  available: true,
  enabled: true,
  connected: true,
  face_id: 'face',
  connector_version: 'version',
  session_length_seconds: 3600,
  connect_timeout_seconds: 15,
};
it('maintains comments through silence and closes on opt-out, never on Radio state', () => {
  expect(avatarDemand('account', config, true, { status: 'idle', session_id: null })?.source).toBe(
    'comments'
  );
  expect(avatarDemand('account', config, false, { status: 'idle', session_id: null })).toBeNull();
  expect(
    avatarDemand('account', { ...config, enabled: false }, true, {
      status: 'idle',
      session_id: null,
    })
  ).toBeNull();
});
it('Live owns both modes and standby suppresses the enabled comments demand', () => {
  const live = avatarDemand('account', config, true, { status: 'listening', session_id: 'live' });
  expect(live).toMatchObject({ source: 'live', live_id: 'live' });
  expect(
    avatarDemand('account', config, true, { status: 'standby', session_id: 'live' })
  ).toBeNull();
  expect(
    sameAvatar(live, avatarDemand('account', config, true, { status: 'idle', session_id: null }))
  ).toBe(true);
  expect(
    sameAvatar(live, avatarDemand('other', config, true, { status: 'idle', session_id: null }))
  ).toBe(false);
});

it('holds only the same owned connection while Live mints, without creating a comments demand for a cold opt-in', () => {
  const previous = avatarDemand('account', config, true, { status: 'idle', session_id: null });
  const preparing = { status: 'minting', session_id: null };
  expect(avatarDemand('account', config, false, preparing, previous)).toBe(previous);
  expect(avatarDemand('account', config, false, preparing)).toBeNull();
  expect(
    avatarDemand('account', { ...config, face_id: 'new-face' }, false, preparing, previous)
  ).toBeNull();
  expect(avatarDemand('other', config, false, preparing, previous)).toBeNull();
  expect(
    avatarDemand('account', config, false, { status: 'error', session_id: null }, previous)
  ).toBeNull();
});
