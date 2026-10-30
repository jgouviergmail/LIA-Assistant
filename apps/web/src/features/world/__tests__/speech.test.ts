import { expect, it } from 'vitest';
import { WorldSpeech, privateSpeechDeliveries, publicSpeechDeliveries } from '../speech';
import { createSimulation, stepSimulation } from '../simulation';
import { WORLD } from '../definition';
import type { WorldMessage, WorldMailbox } from '../message-protocol';
import type { Notification } from '@/hooks/useNotifications';
const message = (
  id: string,
  created: number,
  text: string | null = 'Translated'
): WorldMessage => ({
  id,
  sender_id: 'sender',
  sender_alias: 'Camille',
  recipient_id: 'own',
  recipient_alias: 'Me',
  outgoing: false,
  original: 'DO NOT DISPLAY ORIGINAL',
  text,
  language: 'en',
  status: text ? 'translated' : 'pending',
  created_at: created,
  expires_at: created + 1800,
  receipt: null,
});
const box = (server_time: number, messages: WorldMessage[]): WorldMailbox => ({
  server_time,
  messages,
  truncated: false,
  ttl_seconds: 1800,
});
it('never replays initial history, untranslated incoming text or expired messages', () => {
  const speech = new WorldSpeech();
  speech.setActive(true);
  speech.receive(privateSpeechDeliveries(box(100, [message('old', 99)])), 100, 'private', 0);
  expect(speech.bubbles(0)).toEqual([]);
  speech.receive(
    privateSpeechDeliveries(box(101, [message('old', 99), message('pending', 101, null)])),
    101,
    'private',
    1000
  );
  expect(speech.bubbles(1000)).toEqual([]);
  speech.receive(
    privateSpeechDeliveries(box(103, [message('pending', 101)])),
    103,
    'private',
    3000
  );
  expect(speech.bubbles(3000)[0]?.text).toBe('Translated');
  expect(speech.bubbles(3000)[0]?.text).not.toContain('ORIGINAL');
  expect(speech.bubbles(8000)).toEqual([]);
  // Polling and reconnect reads do not prolong the expired bubble.
  speech.receive(
    privateSpeechDeliveries(box(110, [message('pending', 101)])),
    110,
    'private',
    10000
  );
  expect(speech.bubbles(10000)).toEqual([]);
});
it('replaces one speaker for five monotonic seconds and refuses late older translations', () => {
  const speech = new WorldSpeech();
  speech.setActive(true);
  speech.receive([], 100, 'private', 0);
  speech.receive(privateSpeechDeliveries(box(101, [message('a', 101)])), 101, 'private', 1000);
  speech.receive(
    privateSpeechDeliveries(box(102, [message('b', 102, 'New')])),
    102,
    'private',
    2000
  );
  speech.receive(
    privateSpeechDeliveries(box(103, [message('c', 100, 'Older')])),
    103,
    'private',
    3000
  );
  expect(speech.bubbles(6999).map(x => x.text)).toEqual(['New']);
  expect(speech.bubbles(7000)).toEqual([]);
  speech.setActive(false);
  speech.receive(privateSpeechDeliveries(box(104, [message('d', 104)])), 104, 'private', 4000);
  expect(speech.bubbles(4000)).toEqual([]);
});
const notice = (id = 'event', content = 'A private proactive message'): Notification => ({
  id,
  type: 'proactive_discussion',
  content,
  timestamp: new Date(100000),
  read: false,
  target_id: 'thread',
  metadata: { message_id: id },
});
it('LIA approaches through navigation, waits until the panel closes, and never teleports or starts a provider', () => {
  const speech = new WorldSpeech(),
    sim = createSimulation(WORLD);
  speech.setActive(true);
  const before = { ...sim.bip.position };
  speech.proactive(notice(), 0, 100000);
  speech.advance(sim, 0, true);
  expect(sim.bip.position).toEqual(before);
  expect(sim.noticeFollowing).toBe(true);
  sim.bip.position = { x: sim.player.position.x + 1, y: sim.player.position.y };
  speech.advance(sim, 1000, true);
  expect(speech.bubbles(1000)).toEqual([]);
  speech.advance(sim, 2000, false);
  expect(speech.bubbles(2000)[0]?.kind).toBe('lia');
  speech.proactive(notice(), 3000, 100000); // SSE/FCM duplicate does not extend it.
  speech.advance(sim, 7000, false);
  expect(speech.bubbles(7000)).toEqual([]);
  expect(sim.noticeFollowing).toBe(false);
  stepSimulation(sim, 0.016, { x: 0, y: 0 });
});
it('ignores stale notices, bounds pending movement and clears all content when authority is lost', () => {
  const speech = new WorldSpeech(),
    sim = createSimulation(WORLD);
  speech.setActive(true);
  speech.proactive(notice(), 0, 300000);
  speech.advance(sim, 0, false);
  expect(sim.noticeFollowing).toBe(false);
  speech.proactive(notice('new'), 1000, 100000);
  speech.advance(sim, 1000, false);
  expect(sim.noticeFollowing).toBe(true);
  speech.advance(sim, 62000, false);
  expect(sim.noticeFollowing).toBe(false);
  speech.setActive(false);
  expect(speech.bubbles(62000)).toEqual([]);
  expect(speech.getSnapshot()).toEqual([]);
});

it('allows successive proactive interests whose reusable target has no message id', () => {
  const speech = new WorldSpeech(),
    sim = createSimulation(WORLD);
  speech.setActive(true);
  sim.bip.position = { x: sim.player.position.x + 1, y: sim.player.position.y };
  speech.proactive(
    { ...notice('same-target', 'First opening'), type: 'proactive_interest', metadata: undefined },
    0,
    100000
  );
  speech.advance(sim, 0, false);
  speech.proactive(
    {
      ...notice('same-target', 'Another opening'),
      type: 'proactive_interest',
      metadata: undefined,
    },
    2000,
    100000
  );
  speech.advance(sim, 2000, false);
  expect(speech.bubbles(2000)[0]?.text).toBe('Another opening');
});

it('announces only present actors and clears visible private text when a speaker leaves', () => {
  const speech = new WorldSpeech(),
    sim = createSimulation(WORLD);
  speech.setActive(true);
  speech.receive([], 100, 'private', 0);
  speech.receive(privateSpeechDeliveries(box(101, [message('new', 101)])), 101, 'private', 1000);
  speech.advance(sim, 1000, false);
  expect(speech.getSnapshot()).toEqual([]);
  sim.visitors = [
    {
      ...sim.player,
      id: 'sender',
      label: 'Camille',
      from: sim.player.position,
      target: sim.player.position,
      blend: 0,
    },
  ];
  speech.advance(sim, 1100, false);
  expect(speech.getSnapshot()[0]?.text).toBe('Translated');
  sim.visitors = [];
  speech.advance(sim, 1200, false);
  expect(speech.getSnapshot()).toEqual([]);
  speech.setActive(false);
  expect(speech.bubbles(1200)).toEqual([]);
});

it('bounds presentation memory and ignores malformed or non-proactive notices', () => {
  const speech = new WorldSpeech(),
    sim = createSimulation(WORLD);
  speech.setActive(true);
  speech.receive([], 100, 'private', 0);
  for (let i = 0; i < 140; i++)
    speech.receive(
      [
        {
          id: String(i),
          speaker: String(i),
          label: 'Person',
          text: 'Text',
          ready: true,
          created: 101,
        },
      ],
      101,
      'private',
      1000
    );
  expect(speech.bubbles(1000).length).toBeLessThanOrEqual(128);
  for (const n of [
    { ...notice(), type: 'system' as const },
    { ...notice(), timestamp: new Date(NaN) },
    { ...notice(), metadata: { message_id: 3 } },
    { ...notice(), metadata: { message_id: '' } },
    { ...notice(), content: '   ' },
  ])
    speech.proactive(n, 2000, 100000);
  speech.advance(sim, 2000, false);
  expect(sim.noticeFollowing).toBe(false);
});

it('shows a new public self echo without replaying initial private history', () => {
  const speech = new WorldSpeech();
  speech.setActive(true);
  const publicMessage = {
    audience: 'public' as const,
    ...message('public', 101, 'Hello everyone'),
    outgoing: true,
  };
  const baseline = {
    ...box(100, []),
    public_available: true,
    public_messages: [],
    public_truncated: false,
  };
  speech.receive(publicSpeechDeliveries(baseline), 100, 'public', 0);
  const mailbox = {
    ...box(101, [{ ...message('private', 101), outgoing: true }]),
    public_available: true,
    public_messages: [publicMessage],
  };
  speech.receive(privateSpeechDeliveries(mailbox), 101, 'private', 1000);
  speech.receive(publicSpeechDeliveries(mailbox), 101, 'public', 1000);
  expect(speech.bubbles(1000).map(line => line.text)).toEqual(['Hello everyone']);
  expect(speech.bubbles(6000)).toEqual([]);
});

it.each(['pending', 'failed', 'uncertain', 'unavailable'] as const)(
  'shows both private speakers while recipient translation is %s, without replay or extension',
  status => {
    const speech = new WorldSpeech(),
      sim = createSimulation(WORLD);
    sim.player.publicId = 'own';
    sim.visitors = [
      {
        ...sim.player,
        id: 'sender',
        label: 'Camille',
        from: sim.player.position,
        target: sim.player.position,
        blend: 0,
      },
    ];
    const sent: WorldMessage = {
      ...message('sent', 101, 'My literal reply'),
      sender_id: 'own',
      sender_alias: 'Me',
      recipient_id: 'sender',
      recipient_alias: 'Camille',
      outgoing: true,
      original: 'My literal reply',
      status,
    };
    speech.setActive(true);
    speech.receive(
      privateSpeechDeliveries(box(100, [{ ...sent, id: 'history', created_at: 99 }])),
      100,
      'private',
      0
    );
    expect(speech.bubbles(0)).toEqual([]);
    const messages = [sent, message('incoming', 101)];
    speech.receive(privateSpeechDeliveries(box(101, messages)), 101, 'private', 1000);
    speech.advance(sim, 1000, true); // An open conversation must not hide either speaker.
    expect(
      speech.getSnapshot().map(({ speaker, text, kind }) => ({ speaker, text, kind }))
    ).toEqual([
      { speaker: 'own', text: 'My literal reply', kind: 'private' },
      { speaker: 'sender', text: 'Translated', kind: 'private' },
    ]);
    speech.receive(
      privateSpeechDeliveries(box(102, [{ ...sent, status: 'translated' }, messages[1]!])),
      102,
      'private',
      2000
    );
    speech.advance(sim, 6000, false);
    expect(speech.getSnapshot()).toEqual([]);
    speech.setActive(false);
    speech.setActive(true);
    speech.receive(privateSpeechDeliveries(box(107, messages)), 107, 'private', 7000);
    speech.advance(sim, 7000, false);
    expect(speech.getSnapshot()).toEqual([]);
  }
);

it('public speech waits for ready translated text without an original fallback', () => {
  const base = box(101, []);
  const pending = { audience: 'public' as const, ...message('public-pending', 101, null) };
  const translated = { ...pending, id: 'translated', status: 'translated' as const, text: 'Ready' };
  const original = {
    ...pending,
    id: 'original',
    status: 'original' as const,
    text: 'Same language',
  };
  expect(
    publicSpeechDeliveries({ ...base, public_messages: [pending, translated, original] }).map(
      item => [item.ready, item.text]
    )
  ).toEqual([
    [false, null],
    [true, 'Ready'],
    [true, 'Same language'],
  ]);
});
