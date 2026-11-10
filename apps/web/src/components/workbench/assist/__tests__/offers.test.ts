/**
 * What each tool lists under the question's icon (lot 1): who and what the words name, and the
 * ready-made question left unsent in the chat. A thing still being read offers nothing, so the icon
 * stays the question itself.
 */
import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { DetailDeed } from '../../DetailBar';
import type {
  CalendarEventDetail,
  MailAttachment,
  MailMessage,
  WorkbenchContact,
  WorkbenchFileDetail,
  WorkbenchTask,
} from '@/lib/workbench/types';

const {
  ask,
  remind,
  confide,
  keep,
  watch,
  push,
  start,
  go,
  ready,
  bridges,
  bounds,
  recorder,
  minutes,
} = vi.hoisted(() => ({
  bounds: {
    value: null as null | { textMax: number; instructionMax: number; dictates: boolean },
  },
  ask: vi.fn(),
  remind: vi.fn(),
  confide: vi.fn(),
  keep: vi.fn(),
  watch: vi.fn(),
  push: vi.fn(),
  start: vi.fn(),
  go: vi.fn(),
  // The tools ready to take what is handed to them, by what they take.
  ready: { kinds: [] as string[] },
  bridges: { assists: false, board: false, spaces: false, meetings: false, reads: false },
  recorder: { value: null as null | { isSupported: boolean; phase: string; start: () => void } },
  minutes: {
    items: [] as { id: string }[],
    loading: false,
    asked: [] as { enabled?: boolean; params?: unknown }[],
  },
}));
vi.mock('../../useToolBridges', () => ({
  useToolBridges: () => ({
    ask,
    remind,
    assists: bridges.assists,
    confide: bridges.board ? confide : undefined,
    keep: bridges.spaces ? keep : undefined,
    meetings: bridges.meetings,
    reads: bridges.reads,
    offers: (kind: string) => ready.kinds.includes(kind),
    go,
  }),
}));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'owner', email: 'me@example.org', timezone: 'Europe/Paris' } }),
}));
vi.mock('../../WorkbenchShell', () => ({ useAssistBounds: () => bounds.value }));
// These generic contact lines have no phone; eligibility is supplied at its own boundary.
vi.mock('@/hooks/useTelephonyCallable', () => ({ useTelephonyCallable: () => false }));
vi.mock('@/hooks/useMailWatch', () => ({ useMailWatch: () => ({ watch }) }));
vi.mock('@/hooks/useLocalizedRouter', () => ({ useLocalizedRouter: () => ({ push }) }));
vi.mock('@/components/meetings/MeetingRecorderProvider', () => ({
  useMeetingRecorderContext: () => recorder.value,
}));
vi.mock('@/hooks/useApiQuery', () => ({
  useApiQuery: (_path: string, options: { enabled?: boolean; params?: unknown }) => {
    minutes.asked.push(options);
    return { data: { items: minutes.items }, loading: minutes.loading };
  },
}));
vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, string>) =>
      values ? `${key} ${JSON.stringify(values)}` : key,
  }),
}));

import { useContactAssist } from '../useContactAssist';
import { useEventAssist } from '../useEventAssist';
import { useFileAssist } from '../useFileAssist';
import { useMailAssist } from '../useMailAssist';
import { useTaskAssist } from '../useTaskAssist';

const REMIND = 'workbench.assist.remind.line';

function line(lines: readonly DetailDeed[], starts: string): DetailDeed {
  const found = lines.find(item => item.label.startsWith(starts));
  if (!found) throw new Error(`no line ${starts}`);
  return found;
}

const MESSAGE: MailMessage = {
  id: 'm1',
  thread_id: 't1',
  sender: { name: 'Ana', address: 'ana@example.org' },
  subject: 'Budget',
  received_at: '2026-11-04T09:00:00Z',
  is_read: true,
  is_starred: false,
  has_attachments: false,
  label_ids: [],
  reply_to: [],
  to: [],
  cc: [],
  body: 'Hello',
  attachments: [],
};
const EVENT: CalendarEventDetail = {
  id: 'e1',
  calendar_id: 'c1',
  summary: 'Review',
  all_day: false,
  start: '2026-11-05T09:00:00Z',
  end: '2026-11-05T10:00:00Z',
  location: null,
  recurring: false,
  conference_url: null,
  description: null,
  attendees: [],
  organizer: null,
  link: null,
  reminder_minutes: null,
  busy: true,
  private: false,
  zone: null,
  my_response: null,
};
const TASK: WorkbenchTask = {
  id: 't1',
  title: 'Pay the invoice',
  notes: null,
  completed: false,
  due: null,
  parent: null,
  position: null,
  steps: [],
  importance: null,
  reminder: null,
  repeat: null,
};
const CONTACT: WorkbenchContact = {
  id: 'p1',
  name: 'Ana Silva',
  given_name: null,
  family_name: null,
  email: null,
  phone: null,
  organization: null,
  name_key: 'ana silva',
  emails: [],
  phones: [],
  addresses: [],
  notes: null,
  job_title: null,
  website: null,
  birthday: null,
};
const FILE: WorkbenchFileDetail = {
  id: 'f1',
  name: 'Plan.pdf',
  kind: 'file',
  mime_type: 'application/pdf',
  modified_at: null,
  size: 10,
  web_url: null,
  target_id: null,
  target_kind: null,
  formats: [],
  downloadable: true,
  starred: false,
  previewable: true,
  editable: false,
  owners: [],
  description: null,
  created_at: null,
  ancestors: [],
  in_my_drive: true,
  ancestors_truncated: false,
};

beforeEach(() => {
  vi.clearAllMocks();
  ready.kinds = [];
  bridges.assists = false;
  bridges.board = false;
  bridges.spaces = false;
  bridges.meetings = false;
  bridges.reads = false;
  bounds.value = null;
  recorder.value = null;
  minutes.items = [];
  minutes.loading = false;
  minutes.asked = [];
});

const READ_FILE = 'workbench.assist.file.summary';
const DESCRIBE = 'workbench.assist.file.describe';
const CONVERSATION = 'workbench.assist.mail.conversation';
const WATCH = 'workbench.assist.mail.watch';
const CONFIDE = 'workbench.assist.confide.line';
const KEEP = 'workbench.assist.keep.line';
const MINUTES = 'workbench.assist.calendar.minutes';
const RECORD = 'workbench.assist.calendar.record';

function labels(lines: readonly DetailDeed[]): string[] {
  return lines.map(item => item.label);
}

describe('reading a message aloud (lot 8)', () => {
  const doors = { onPropose: vi.fn() };
  const READ = 'workbench.assist.voice.read';

  it('offers it where a click may ask and a voice exists, on a message with words', () => {
    bridges.assists = true;
    bounds.value = { textMax: 100, instructionMax: 10, dictates: true };
    expect(
      labels(renderHook(() => useMailAssist('en', MESSAGE, doors)).result.current.lines)
    ).not.toContain(READ);

    bridges.reads = true;
    const { lines } = renderHook(() => useMailAssist('en', MESSAGE, doors)).result.current;
    expect(labels(lines)).toContain(READ);

    const blank = { ...MESSAGE, body: '  ' };
    expect(
      labels(renderHook(() => useMailAssist('en', blank, doors)).result.current.lines)
    ).not.toContain(READ);
  });
});

describe('what LIA reads (lot 6)', () => {
  const doors = { onPropose: vi.fn() };
  const PDF: MailAttachment = {
    id: 'a1',
    filename: 'Bill.pdf',
    mime_type: 'application/pdf',
    size: 10,
    previewable: true,
  };

  it('sums up a file where a click may ask a model, and describes an image', () => {
    expect(labels(renderHook(() => useFileAssist('en', FILE)).result.current.lines)).not.toContain(
      READ_FILE
    );

    bridges.assists = true;
    const { lines } = renderHook(() => useFileAssist('en', FILE)).result.current;
    expect(labels(lines)).toContain(READ_FILE);

    const photo = { ...FILE, mime_type: 'image/jpeg' };
    const image = renderHook(() => useFileAssist('en', photo)).result.current;
    expect(labels(image.lines)).toContain(DESCRIBE);
    expect(labels(image.lines)).not.toContain(READ_FILE);
  });

  it('offers no reading of what has nothing to show', () => {
    bridges.assists = true;
    const opaque = { ...FILE, previewable: false };
    const { lines } = renderHook(() => useFileAssist('en', opaque)).result.current;
    expect(labels(lines)).not.toContain(READ_FILE);
  });

  it('sums up a conversation only once it holds more than one message', () => {
    bridges.assists = true;
    const alone = renderHook(() => useMailAssist('en', MESSAGE, { ...doors, said: 1 })).result
      .current;
    expect(labels(alone.lines)).not.toContain(CONVERSATION);

    const many = renderHook(() => useMailAssist('en', MESSAGE, { ...doors, said: 3 })).result
      .current;
    expect(labels(many.lines)).toContain(CONVERSATION);
  });

  it('offers on a file of the message what its door can do', () => {
    const closed = renderHook(() => useMailAssist('en', MESSAGE, doors)).result.current;
    expect(closed.attachmentLines(PDF, 'Bill.pdf')).toEqual([]);

    bridges.assists = true;
    bridges.spaces = true;
    const open = renderHook(() => useMailAssist('en', MESSAGE, doors)).result.current;
    const lines = open.attachmentLines(PDF, 'Bill.pdf');
    expect(labels(lines)).toEqual([READ_FILE, KEEP]);

    line(lines, KEEP).onSelect?.();
    expect(keep).toHaveBeenCalledWith({
      kind: 'attachment',
      name: 'Bill.pdf',
      filename: 'Bill.pdf',
      message_id: 'm1',
      attachment_id: 'a1',
    });
  });

  it('keeps what cannot be shown, and reads only what can', () => {
    bridges.assists = true;
    bridges.spaces = true;
    const opaque = { ...PDF, previewable: false };
    const { attachmentLines } = renderHook(() => useMailAssist('en', MESSAGE, doors)).result
      .current;

    expect(labels(attachmentLines(opaque, 'Bill.pdf'))).toEqual([KEEP]);
  });
});

describe('the bridges to what LIA already does (lot 5)', () => {
  const doors = { onPropose: vi.fn() };

  it('waits for a received message’s sender, and for the first recipient of a sent one', () => {
    const received = renderHook(() => useMailAssist('en', MESSAGE, doors)).result.current;
    line(received.lines, WATCH).onSelect?.();
    expect(watch).toHaveBeenLastCalledWith(
      { sender_email: 'ana@example.org', sender_name: 'Ana' },
      'Ana'
    );

    const mine: MailMessage = {
      ...MESSAGE,
      sender: { name: 'Me', address: 'me@example.org' },
      to: [{ name: '', address: 'bob@example.org' }],
    };
    const sent = renderHook(() => useMailAssist('en', mine, { ...doors, sent: true })).result
      .current;
    line(sent.lines, WATCH).onSelect?.();
    expect(watch).toHaveBeenLastCalledWith(
      { sender_email: 'bob@example.org', sender_name: '' },
      'bob@example.org'
    );
  });

  it('offers no watch when nobody can be waited for', () => {
    const nobody: MailMessage = { ...MESSAGE, sender: null };
    const { lines } = renderHook(() => useMailAssist('en', nobody, doors)).result.current;
    expect(labels(lines)).not.toContain(WATCH);
    const unsent = renderHook(() => useMailAssist('en', MESSAGE, { ...doors, sent: true })).result
      .current;
    expect(labels(unsent.lines)).not.toContain(WATCH);
  });

  it('hands a thing to LIA only where the board is on, its words filled', () => {
    const closed = renderHook(() => useMailAssist('en', MESSAGE, doors)).result.current;
    expect(labels(closed.lines)).not.toContain(CONFIDE);

    bridges.board = true;
    const zoned = { ...doors, zone: 'Europe/Paris' };
    const mail = renderHook(() => useMailAssist('en', MESSAGE, zoned)).result.current;
    line(mail.lines, CONFIDE).onSelect?.();
    expect(confide).toHaveBeenLastCalledWith({
      title: 'Budget',
      brief: expect.stringMatching(
        /^workbench\.assist\.confide\.brief_mail_on \{"sender":"Ana","subject":"Budget","when":"Nov 4, 2026, 10:00\sAM"\}$/
      ),
    });

    const undated = { ...MESSAGE, received_at: null };
    const unknown = renderHook(() => useMailAssist('en', undated, zoned)).result.current;
    line(unknown.lines, CONFIDE).onSelect?.();
    expect(confide).toHaveBeenLastCalledWith({
      title: 'Budget',
      brief: 'workbench.assist.confide.brief_mail {"sender":"Ana","subject":"Budget"}',
    });

    const noted = { ...TASK, notes: 'Before Friday' };
    const task = renderHook(() => useTaskAssist('en', noted)).result.current;
    line(task.lines, CONFIDE).onSelect?.();
    expect(confide).toHaveBeenLastCalledWith({ title: 'Pay the invoice', brief: 'Before Friday' });
  });

  it('keeps what has bytes, where spaces are on', () => {
    expect(labels(renderHook(() => useFileAssist('en', FILE)).result.current.lines)).not.toContain(
      KEEP
    );

    bridges.spaces = true;
    const { lines } = renderHook(() => useFileAssist('en', FILE)).result.current;
    line(lines, KEEP).onSelect?.();
    expect(keep).toHaveBeenCalledWith({ kind: 'file', name: 'Plan.pdf', file_id: 'f1' });

    const folder = { ...FILE, downloadable: false };
    expect(
      labels(renderHook(() => useFileAssist('en', folder)).result.current.lines)
    ).not.toContain(KEEP);
  });

  it('reads no minutes where meetings are off, and asks by the event where they are on', () => {
    recorder.value = { isSupported: true, phase: 'idle', start };
    renderHook(() => useEventAssist('en', EVENT, 'UTC'));
    expect(minutes.asked.at(-1)?.enabled).toBe(false);

    bridges.meetings = true;
    minutes.items = [{ id: 'meeting-1' }];
    const { lines } = renderHook(() => useEventAssist('en', EVENT, 'UTC')).result.current;

    expect(minutes.asked.at(-1)).toMatchObject({
      enabled: true,
      params: { calendar_event_id: 'e1', limit: 1 },
    });
    line(lines, MINUTES).onSelect?.();
    expect(push).toHaveBeenCalledWith('/dashboard/meetings/meeting-1');
  });

  it('says nothing of minutes while they are being read', () => {
    bridges.meetings = true;
    minutes.items = [{ id: 'the-previous-event-s' }];
    minutes.loading = true;

    const { lines } = renderHook(() => useEventAssist('en', EVENT, 'UTC')).result.current;

    expect(labels(lines)).not.toContain(MINUTES);
  });

  it('offers to record a meeting about to happen, and nothing else', () => {
    const inTenMinutes = {
      ...EVENT,
      start: new Date(Date.now() + 10 * 60_000).toISOString(),
      end: new Date(Date.now() + 70 * 60_000).toISOString(),
    };
    bridges.meetings = true;
    recorder.value = { isSupported: true, phase: 'idle', start };
    const { lines } = renderHook(() => useEventAssist('en', inTenMinutes, 'UTC')).result.current;
    line(lines, RECORD).onSelect?.();
    expect(start).toHaveBeenCalledOnce();

    bridges.meetings = false;
    const closed = renderHook(() => useEventAssist('en', inTenMinutes, 'UTC')).result.current;
    expect(labels(closed.lines)).not.toContain(RECORD);
    bridges.meetings = true;

    const past = renderHook(() => useEventAssist('en', EVENT, 'UTC')).result.current;
    expect(labels(past.lines)).not.toContain(RECORD);

    recorder.value = { isSupported: true, phase: 'recording', start };
    const busy = renderHook(() => useEventAssist('en', inTenMinutes, 'UTC')).result.current;
    expect(labels(busy.lines)).not.toContain(RECORD);

    recorder.value = { isSupported: false, phase: 'idle', start };
    const refused = renderHook(() => useEventAssist('en', inTenMinutes, 'UTC')).result.current;
    expect(labels(refused.lines)).not.toContain(RECORD);
  });
});

const DOORS = { onPropose: vi.fn() };

describe('the lines of a message', () => {
  it('offers nothing while the message is being read', () => {
    const { result } = renderHook(() => useMailAssist('en', undefined, DOORS));

    expect(result.current.lines).toEqual([]);
  });

  it('remembers who wrote and what about', () => {
    const { result } = renderHook(() => useMailAssist('en', MESSAGE, DOORS));

    line(result.current.lines, REMIND).onSelect?.();

    expect(remind).toHaveBeenCalledWith(
      'workbench.assist.remind.words.mail {"sender":"Ana","subject":"Budget"}'
    );
  });

  it('leaves the ready-made question unsent in the chat, in the question’s group', () => {
    const { result } = renderHook(() => useMailAssist('en', MESSAGE, DOORS));

    const ready = line(result.current.lines, 'workbench.ask.ready.mail');
    ready.onSelect?.();

    expect(ready.asks).toBe(true);
    expect(ask).toHaveBeenCalledWith(
      'workbench.ask.ready.mail_words {"sender":"Ana","subject":"Budget"}'
    );
  });

  it('never leaves a blank where the message has no subject', () => {
    const { result } = renderHook(() =>
      useMailAssist('en', { ...MESSAGE, subject: '', sender: null }, DOORS)
    );

    line(result.current.lines, REMIND).onSelect?.();

    expect(remind).toHaveBeenCalledWith(
      'workbench.assist.remind.words.mail {"sender":"","subject":"workbench.mail.no_subject"}'
    );
  });
});

describe('the lines of a message, a model being offered', () => {
  const SUMMARY = 'workbench.assist.mail.summary';
  const REPLY = 'workbench.assist.mail.reply';

  it('offers nothing a model would answer while the switch is off', () => {
    const { result } = renderHook(() => useMailAssist('en', MESSAGE, DOORS));

    expect(result.current.lines.map(item => item.label)).not.toContain(SUMMARY);
    expect(result.current.lines.map(item => item.label)).not.toContain(REPLY);
  });

  it('leads with what LIA does on the message itself', () => {
    bridges.assists = true;
    const { result } = renderHook(() => useMailAssist('en', MESSAGE, DOORS));

    expect(result.current.lines.slice(0, 3).map(item => item.label)).toEqual([
      SUMMARY,
      'workbench.assist.mail.translate',
      REPLY,
    ]);
  });

  it('opens the answer with a proposal on its way, and reads nothing itself', () => {
    bridges.assists = true;
    const { result } = renderHook(() => useMailAssist('en', MESSAGE, DOORS));

    line(result.current.lines, REPLY).onSelect?.();

    expect(DOORS.onPropose).toHaveBeenCalledWith(MESSAGE);
  });
});

describe('the lines of an event', () => {
  it('names it and when it is, on the account’s wall', () => {
    const { result } = renderHook(() => useEventAssist('en', EVENT, 'Europe/Paris'));

    line(result.current.lines, 'workbench.ask.ready.event').onSelect?.();

    expect(ask.mock.calls[0][0]).toContain('"title":"Review"');
    expect(ask.mock.calls[0][0]).toContain('"when":"');
  });

  it('offers nothing while the event is being read', () => {
    const { result } = renderHook(() => useEventAssist('en', undefined, 'Europe/Paris'));

    expect(result.current.lines).toEqual([]);
  });
});

describe('the lines of a task', () => {
  it('reminds of its title as it stands', () => {
    const { result } = renderHook(() => useTaskAssist('en', TASK));

    line(result.current.lines, REMIND).onSelect?.();
    line(result.current.lines, 'workbench.ask.ready.task').onSelect?.();

    expect(remind).toHaveBeenCalledWith('Pay the invoice');
    expect(ask).toHaveBeenCalledWith('workbench.ask.ready.task_words {"title":"Pay the invoice"}');
  });
});

describe('the lines of a contact', () => {
  it('names the person', () => {
    const { result } = renderHook(() => useContactAssist('en', CONTACT));

    line(result.current.lines, REMIND).onSelect?.();
    line(result.current.lines, 'workbench.ask.ready.contact').onSelect?.();

    expect(remind).toHaveBeenCalledWith(
      'workbench.assist.remind.words.contact {"name":"Ana Silva"}'
    );
    expect(ask).toHaveBeenCalledWith('workbench.ask.ready.contact_words {"name":"Ana Silva"}');
  });

  it('offers nothing while the contact is being read', () => {
    const { result } = renderHook(() => useContactAssist('en', undefined));

    expect(result.current.lines).toEqual([]);
  });
});

describe('the lines of a file', () => {
  it('names the file', () => {
    const { result } = renderHook(() => useFileAssist('en', FILE));

    line(result.current.lines, REMIND).onSelect?.();

    expect(remind).toHaveBeenCalledWith('workbench.assist.remind.words.file {"name":"Plan.pdf"}');
  });
});

describe('lot 5 — an event, a task and a file lead to the other tools (2026-11-07)', () => {
  const WRITE_GUESTS = 'workbench.assist.calendar.write_guests';
  const BLOCK = 'workbench.assist.tasks.block_slot';
  const MAIL_WITH_LIA = 'workbench.assist.file.mail_with_lia';
  const GUESTS: CalendarEventDetail = {
    ...EVENT,
    attendees: [
      { email: 'ana@example.org', name: 'Ana', response: 'accepted' },
      { email: 'ME@example.org', name: null, response: 'accepted' },
      { email: 'ana@example.org', name: 'Ana', response: 'accepted' },
    ],
    organizer: 'bo@example.org',
  };

  it('writes to the event’s guests with LIA, each once and the person left out', () => {
    bridges.assists = true;
    ready.kinds = ['compose'];
    const { lines } = renderHook(() => useEventAssist('en', GUESTS, 'Europe/Paris')).result.current;

    line(lines, WRITE_GUESTS).onSelect?.();

    expect(go).toHaveBeenCalledWith({
      kind: 'compose',
      to: 'ana@example.org, bo@example.org',
      subject: 'Review',
      assisted: true,
    });
  });

  it('offers no writing to guests without any, without the assists, or without a mailbox', () => {
    const offered = (event: CalendarEventDetail) =>
      labels(renderHook(() => useEventAssist('en', event, 'Europe/Paris')).result.current.lines);

    bridges.assists = true;
    ready.kinds = ['compose'];
    expect(offered({ ...EVENT, attendees: [], organizer: 'me@example.org' })).not.toContain(
      WRITE_GUESTS
    );
    bridges.assists = false;
    expect(offered(GUESTS)).not.toContain(WRITE_GUESTS);
    bridges.assists = true;
    ready.kinds = [];
    expect(offered(GUESTS)).not.toContain(WRITE_GUESTS);
  });

  it('blocks a slot for a task on its coming day, at nine, the calendar opening on it', () => {
    ready.kinds = ['event'];
    const due = { ...TASK, due: '2099-01-15', notes: 'Invoice 118' };
    const { lines } = renderHook(() => useTaskAssist('en', due, undefined, 'Europe/Paris')).result
      .current;

    line(lines, BLOCK).onSelect?.();

    expect(go).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: 'event',
        summary: 'Pay the invoice',
        description: 'Invoice 118',
        proposal: expect.objectContaining({
          summary: 'Pay the invoice',
          start_date: '2099-01-15',
          start_time: '09:00',
          all_day: false,
        }),
      })
    );
  });

  it('blocks today for a task with no coming day, the editor choosing the hour', () => {
    ready.kinds = ['event'];
    const late = { ...TASK, due: '2001-01-15' };

    for (const task of [TASK, late]) {
      go.mockClear();
      const { lines } = renderHook(() => useTaskAssist('en', task, undefined, 'Europe/Paris'))
        .result.current;
      line(lines, BLOCK).onSelect?.();

      expect(go).toHaveBeenCalledWith({
        kind: 'event',
        summary: 'Pay the invoice',
        description: '',
      });
    }
  });

  it('offers no slot without a calendar, for a task done, or one with no title', () => {
    const offered = (task: WorkbenchTask) =>
      labels(
        renderHook(() => useTaskAssist('en', task, undefined, 'Europe/Paris')).result.current.lines
      );

    expect(offered(TASK)).not.toContain(BLOCK);
    ready.kinds = ['event'];
    expect(offered({ ...TASK, completed: true })).not.toContain(BLOCK);
    expect(offered({ ...TASK, title: '' })).not.toContain(BLOCK);
  });

  it('sends a file in a message written with LIA, within what a message carries', () => {
    bridges.assists = true;
    ready.kinds = ['compose'];
    const { lines } = renderHook(() => useFileAssist('en', FILE, 1000)).result.current;

    line(lines, MAIL_WITH_LIA).onSelect?.();

    expect(go).toHaveBeenCalledWith({
      kind: 'compose',
      to: '',
      file: {
        id: 'f1',
        filename: 'Plan.pdf',
        mime_type: 'application/pdf',
        size: 10,
        origin: 'drive',
        expires_at: null,
      },
      assisted: true,
    });
  });

  it('offers no message with LIA past the bound, for a file that cannot leave, or without the assists', () => {
    const offered = (file: WorkbenchFileDetail, max?: number) =>
      labels(renderHook(() => useFileAssist('en', file, max)).result.current.lines);

    bridges.assists = true;
    ready.kinds = ['compose'];
    expect(offered(FILE, 5)).not.toContain(MAIL_WITH_LIA);
    expect(offered({ ...FILE, downloadable: false }, 1000)).not.toContain(MAIL_WITH_LIA);
    expect(offered(FILE)).not.toContain(MAIL_WITH_LIA);
    bridges.assists = false;
    expect(offered(FILE, 1000)).not.toContain(MAIL_WITH_LIA);
  });
});
