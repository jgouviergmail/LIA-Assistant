import assert from 'node:assert/strict';
import test from 'node:test';
import { mascotDirection } from '../src/mascot-direction.ts';
import { avatarContextAt } from '../src/avatar-context.ts';

test('the stage mascot looks toward the product on either side', () => {
  const left = mascotDirection({ screenSide: 'left' });
  const right = mascotDirection({ screenSide: 'right' });
  assert.ok(left.gazeX < -0.6 && left.headYaw < -0.6);
  assert.ok(right.gazeX > 0.6 && right.headYaw > 0.6);
  assert.equal(left.gazeX, -right.gazeX);
});

test('a crossing keeps its initial facing and lets eyes lead the head', () => {
  const start = mascotDirection({ screenSide: 'left', previousScreenSide: 'right', turnProgress: 0 });
  const crossing = mascotDirection({ screenSide: 'left', previousScreenSide: 'right', turnProgress: 0.5 });
  const arrived = mascotDirection({ screenSide: 'left', previousScreenSide: 'right', turnProgress: 1 });
  assert.ok(start.gazeX > 0 && start.headYaw > 0);
  assert.ok(crossing.gazeX < 0 && crossing.headYaw > 0);
  assert.ok(arrived.gazeX < 0 && arrived.headYaw < 0);
  assert.deepEqual(arrived, mascotDirection({ screenSide: 'left' }));
});

test('a viewer glance is face-on and a full context reel includes voice states', () => {
  const viewer = mascotDirection({ screenSide: 'left', audienceWeight: 1 });
  assert.equal(viewer.gazeX, 0);
  assert.equal(viewer.headYaw, 0);
  assert.equal(avatarContextAt(14, 15).inputs.voiceState, 'speaking');
  assert.equal(avatarContextAt(11, 15).inputs.voiceState, 'recording');
  assert.equal(avatarContextAt(1, 6.5).inputs.userTyping, true);
  assert.equal(avatarContextAt(3, 6.5).inputs.chatStatus, 'streaming');
  assert.equal(avatarContextAt(5, 6.5).inputs.reaction, 'joy');
});
