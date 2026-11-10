/** Fictional, populated Tools journeys using the application's actual wire contracts. */
import type {
  CalendarEvent,
  MailMessage,
  MailSummary,
  WorkbenchAvailability,
  WorkbenchContact,
  WorkbenchDriveItem,
  WorkbenchFileDetail,
  WorkbenchLights,
} from '../../src/lib/workbench/types';
import type { MailSummaryAnswer } from '../../src/lib/workbench/assist';

export const WORKFLOW_NAMES = [
  'tools',
  'tools-mail-menu',
  'tools-mail-assist',
  'tools-calendar',
  'tools-tasks',
  'tools-contacts',
  'tools-files',
  'tools-lights',
  'dashboard-actions',
] as const;

const availability: WorkbenchAvailability = {
  tools: [
    {
      tool: 'mail',
      state: 'ready',
      provider: 'google_gmail',
      features: [
        'mark_read',
        'drafts',
        'attachments',
        'attachment_filter',
        'labels',
        'vacation',
        'vacation_subject',
        'vacation_open_end',
        'filters',
        'filter_words',
      ],
      bounds: {
        search_max_chars: 500,
        assist_text_max_chars: 8000,
        assist_instruction_max_chars: 500,
        recipient_query_min_chars: 2,
        recipients_max: 100,
        recipient_max_chars: 320,
        subject_max_chars: 998,
        body_max_chars: 100000,
        attachments_max: 10,
        attachments_max_bytes: 26214400,
      },
    },
    {
      tool: 'calendar',
      state: 'ready',
      provider: 'google_calendar',
      features: [
        'all_day',
        'conference',
        'notify_attendees',
        'occurrence_edit',
        'event_move',
        'calendar_management',
      ],
      bounds: {
        summary_max_chars: 1024,
        series_max_count: 730,
        location_max_chars: 1024,
        description_max_chars: 8192,
        attendees_max: 100,
        recipient_query_min_chars: 2,
      },
    },
    {
      tool: 'tasks',
      state: 'ready',
      provider: 'google_tasks',
      features: ['list_management', 'subtasks', 'due_date_only', 'task_order'],
      bounds: { title_max_chars: 1024, notes_max_chars: 8192 },
    },
    {
      tool: 'contacts',
      state: 'ready',
      provider: 'google_contacts',
      features: ['multi_valued', 'contact_groups', 'export'],
      bounds: { name_max_chars: 1024, notes_max_chars: 8192 },
    },
    {
      tool: 'files',
      state: 'ready',
      provider: 'google_drive',
      features: ['file_views'],
      bounds: { name_max_chars: 255, text_max_chars: 100000 },
    },
    { tool: 'lights', state: 'ready', provider: 'philips_hue', features: ['scenes'], bounds: {} },
  ],
  limits: {
    page_size: 25,
    bulk_max_items: 50,
    download_max_bytes: 26214400,
    upload_max_bytes: 26214400,
    calendar_window_max_events: 500,
    send_undo_seconds: 10,
    draft_autosave_seconds: 0,
    search_max_chars: 500,
    assist_text_max_chars: 8000,
    assist_instruction_max_chars: 500,
  },
};

export const MAIL_SUBJECT = 'Atlas launch — decisions for Monday';
const mails: MailSummary[] = [
  [
    'Morgan Demo',
    'morgan',
    MAIL_SUBJECT,
    'The prototype is approved. Three decisions remain before launch.',
  ],
  [
    'Sam Demo',
    'sam',
    'Design review — annotated prototype',
    'The accessible navigation and card layouts are ready for review.',
  ],
  [
    'Studio North',
    'studio',
    'Supplier delivery — updated schedule',
    'We can confirm delivery on 22 October, subject to your approval.',
  ],
  [
    'Alex Demo',
    'alex',
    'Friday review — minutes and next steps',
    'Decisions, owners and the updated project checklist.',
  ],
  [
    'City Gallery',
    'gallery',
    'Your photography workshop on Saturday',
    'Your place is reserved for the morning session at 10:00.',
  ],
  [
    'Morgan Demo',
    'morgan',
    'Re: Atlas launch — decisions for Monday',
    'Thanks for the review. I have attached the revised launch budget.',
  ],
  [
    'Sam Demo',
    'sam',
    'Weekend walk — meeting at Bellecour',
    'Shall we meet at 09:30 and walk along the river?',
  ],
  [
    'Demo Library',
    'library',
    'Your reading list for October',
    'Three new titles on design, photography and urban nature.',
  ],
].map(([name, address, subject, snippet], index) => ({
  id: `capture-mail-${index}`,
  thread_id: index === 5 ? 'capture-mail-0' : `capture-mail-${index}`,
  sender: { name, address: `${address}@example.test` },
  subject,
  snippet,
  received_at: `2026-10-${index < 4 ? '12' : '11'}T${String(index < 4 ? 7 - index : 17 - index).padStart(2, '0')}:10:00Z`,
  is_read: index > 2,
  is_starred: index === 0 || index === 4,
  has_attachments: index === 0 || index === 1,
  label_ids: [index < 4 || index === 5 ? 'atlas' : 'personal'],
}));

const message: MailMessage = {
  ...mails[0],
  is_read: true,
  reply_to: [],
  to: [{ name: 'Alex Demo', address: 'alex@example.test' }],
  cc: [{ name: 'Sam Demo', address: 'sam@example.test' }],
  body: 'Hi Alex,\n\nThe prototype passed Friday’s design review. Before the 10:00 meeting, could we settle these three points?\n\n1. Delivery — the project brief targets 19 October, while Studio North proposes 22 October.\n2. Budget — the revised estimate is €4,800, including the photography workshop.\n3. Accessibility — Sam has completed the keyboard and mobile checks.\n\nPlease confirm the delivery date with the supplier and review the attached launch checklist. I will update the team after our meeting.\n\nThanks,\nMorgan',
  attachments: [
    {
      id: 'capture-attachment-1',
      filename: 'Atlas launch checklist.pdf',
      mime_type: 'application/pdf',
      size: 186368,
      previewable: true,
    },
    {
      id: 'capture-attachment-2',
      filename: 'Launch budget.xlsx',
      mime_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      size: 65536,
      previewable: true,
    },
  ],
};

const summary: MailSummaryAnswer = {
  gist: 'The Atlas prototype is approved. The delivery date and revised budget need your decision before the team review.',
  key_points: [
    'The project brief says 19 October; the supplier proposes 22 October.',
    'The revised launch estimate is €4,800.',
    'Keyboard and mobile accessibility checks are complete.',
  ],
  actions: [
    'Confirm the delivery date with Studio North.',
    'Review the attached launch checklist before 10:00.',
  ],
  usage: {
    model_name: 'gpt-4.1-mini',
    tokens_in: 680,
    tokens_out: 124,
    tokens_cache: 320,
    cost_eur: 0.00042,
  },
};

const calendars = [
  {
    id: 'primary',
    name: 'Alex · Personal',
    color: '#7c3aed',
    primary: true,
    writable: true,
    manageable: false,
  },
  {
    id: 'atlas',
    name: 'Project Atlas',
    color: '#059669',
    primary: false,
    writable: true,
    manageable: true,
  },
];
const events: CalendarEvent[] = [
  ['12', '08', '09', 'Design review', 'atlas'],
  ['12', '12', '13', 'Project check-in', 'atlas'],
  ['13', '09', '10', 'Supplier delivery call', 'atlas'],
  ['13', '14', '15', 'Photography exhibition', 'primary'],
  ['14', '08', '10', 'Prototype workshop', 'atlas'],
  ['14', '12', '13', 'Lunch with Sam', 'primary'],
  ['15', '09', '10', 'Launch budget review', 'atlas'],
  ['15', '14', '15', 'Team retrospective', 'atlas'],
  ['16', '08', '09', 'Accessibility review', 'atlas'],
  ['16', '13', '14', 'Weekly planning', 'primary'],
  ['17', '08', '10', 'Photography workshop', 'primary'],
].map(([day, start, end, title, calendar], index) => ({
  id: `capture-event-${index}`,
  calendar_id: calendar,
  summary: title,
  all_day: false,
  start: `2026-10-${day}T${start}:${index === 1 ? '30' : '00'}:00Z`,
  end: `2026-10-${day}T${end}:00:00Z`,
  location: calendar === 'atlas' ? 'Demo Studio' : 'Lyon',
  recurring: index === 9,
  conference_url: index === 2 ? 'https://example.test/meet/atlas' : null,
}));

const tasks = [
  'Confirm the supplier delivery date',
  'Review the launch budget',
  'Send the annotated prototype',
  'Prepare the accessibility checklist',
  'Book the team review room',
  'Collect feedback from Sam',
  'Update the project brief',
  'Share the final launch checklist',
].map((title, index) => ({
  id: `capture-task-${index}`,
  title,
  notes: index === 0 ? 'Compare the supplier proposal with the date in the project brief.' : null,
  completed: index === 6,
  due: `2026-10-${12 + Math.floor(index / 3)}`,
  parent: null,
  position: String(index),
  steps: [],
  importance: null,
  reminder: null,
  repeat: null,
}));

const contacts: WorkbenchContact[] = [
  'Morgan',
  'Sam',
  'Camille',
  'Theo',
  'Ines',
  'Jamie',
  'Robin',
].map((name, index) => ({
  id: `people/capture-${index}`,
  name: `${name} Demo`,
  given_name: name,
  family_name: 'Demo',
  email: `${name.toLowerCase()}@example.test`,
  phone: null,
  organization: index < 4 ? 'Project Atlas' : 'Photography club',
  name_key: `${name.toLowerCase()} demo`,
  emails: [{ value: `${name.toLowerCase()}@example.test`, type: 'work' }],
  phones: [],
  addresses: [],
  notes: 'Fictional contact for the public application walkthrough.',
  job_title: index === 0 ? 'Project coordinator' : null,
  website: null,
  birthday: index === 1 ? '1991-10-12' : null,
}));

const files: WorkbenchDriveItem[] = [
  'Project Atlas',
  'Photography',
  'Launch checklist.pdf',
  'Launch budget.xlsx',
  'Design review.docx',
  'Meeting notes.md',
  'Supplier proposal.pdf',
  'Accessibility report.pdf',
].map((name, index) => ({
  id: `capture-file-${index}`,
  name,
  kind: index < 2 ? 'folder' : 'file',
  mime_type:
    index < 2
      ? 'application/vnd.google-apps.folder'
      : name.endsWith('.md')
        ? 'text/markdown'
        : name.endsWith('.xlsx')
          ? 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
          : name.endsWith('.docx')
            ? 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            : 'application/pdf',
  modified_at: '2026-10-12T07:10:00Z',
  size: index < 2 ? null : 42000 * index,
  web_url: null,
  target_id: null,
  target_kind: null,
  formats: [],
  downloadable: index >= 2,
  starred: index === 2,
  previewable: index >= 2,
  editable: index === 5,
}));

const lights: WorkbenchLights = {
  rooms: [
    {
      id: 'living',
      name: 'Living room',
      kind: 'room',
      light_ids: ['floor', 'reading'],
      on: true,
      supports_color: true,
      mirek_min: 153,
      mirek_max: 500,
    },
    {
      id: 'office',
      name: 'Home office',
      kind: 'room',
      light_ids: ['desk', 'shelf'],
      on: true,
      supports_color: true,
      mirek_min: 153,
      mirek_max: 500,
    },
  ],
  lights: [
    ['floor', 'Floor lamp', 'living'],
    ['reading', 'Reading corner', 'living'],
    ['desk', 'Desk lamp', 'office'],
    ['shelf', 'Bookshelf', 'office'],
  ].map(([id, name, room_id], index) => ({
    id,
    name,
    room_id,
    on: true,
    brightness: [65, 80, 90, 35][index],
    supports_color: true,
    color_hex: ['#ffd39b', '#ffdeae', '#fff1d0', '#c5b2ff'][index],
    mirek: 350,
    mirek_min: 153,
    mirek_max: 500,
    reachable: true,
  })),
  scenes: [
    { id: 'relax', name: 'Relax', room_id: 'living', active: true, dynamic: false, playing: false },
    {
      id: 'reading-scene',
      name: 'Reading',
      room_id: 'living',
      active: false,
      dynamic: false,
      playing: false,
    },
    { id: 'focus', name: 'Focus', room_id: 'office', active: true, dynamic: false, playing: false },
  ],
};

const budgetFile: WorkbenchFileDetail = {
  ...files[3],
  owners: ['Alex Demo'],
  description: 'Revised launch estimate for Project Atlas.',
  created_at: '2026-10-09T12:00:00Z',
  ancestors: [{ id: 'capture-file-0', name: 'Project Atlas' }],
  in_my_drive: true,
  ancestors_truncated: false,
};

/** Exact endpoint fixtures: unknown API routes still fail the browser campaign. */
export function workflowScreenshotRoutes(): { url: string; json: unknown }[] {
  return [
    { url: '**/api/v1/workbench', json: availability },
    {
      url: '**/api/v1/workbench/mail/folders',
      json: {
        folders: [
          ...['inbox', 'starred', 'sent', 'drafts', 'spam', 'trash'].map(role => ({
            id: `system:${role}`,
            kind: 'system',
            role,
            name: null,
          })),
          { id: 'atlas', kind: 'user', role: null, name: 'Project Atlas' },
          { id: 'personal', kind: 'user', role: null, name: 'Personal' },
        ],
      },
    },
    {
      url: '**/api/v1/workbench/mail/counts',
      json: { counts: { 'system:inbox': 3, atlas: 3 }, truncated: false },
    },
    {
      url: '**/api/v1/workbench/mail/messages?*',
      json: { items: mails, next_page_token: null, skipped: 0 },
    },
    { url: '**/api/v1/workbench/mail/message?*', json: message },
    { url: '**/api/v1/workbench/mail/message/html?*', json: { html: null, truncated: false } },
    {
      url: '**/api/v1/workbench/mail/message/unsubscribe?*',
      json: { web_url: null, mail_to: null, one_click: false },
    },
    {
      url: '**/api/v1/workbench/mail/conversation?*',
      json: { items: [mails[5], mails[0]], truncated: false },
    },
    { url: '**/api/v1/workbench/mail/signature', json: { text: 'Alex Demo', html: null } },
    { url: '**/api/v1/workbench/mail/read-state', json: { done: ['capture-mail-0'], failed: [] } },
    { url: '**/api/v1/tool-assists/mail/summary', json: summary },
    { url: '**/api/v1/workbench/calendar/calendars', json: { calendars } },
    {
      url: '**/api/v1/workbench/calendar/events?*',
      json: {
        calendars: calendars.map(calendar => ({
          calendar_id: calendar.id,
          events: events.filter(event => event.calendar_id === calendar.id),
          truncated: false,
          skipped: 0,
          error: null,
        })),
      },
    },
    {
      url: '**/api/v1/workbench/tasks/due?*',
      json: {
        tasks: tasks
          .filter(task => !task.completed)
          .map(task => ({ id: task.id, list_id: 'atlas', title: task.title, due: task.due })),
        truncated: false,
        failed: [],
      },
    },
    {
      url: '**/api/v1/workbench/tasks/lists*',
      json: {
        items: [
          { id: 'atlas', title: 'Project Atlas' },
          { id: 'personal', title: 'Personal' },
        ],
        next_page_token: null,
      },
    },
    {
      url: '**/api/v1/workbench/tasks/view*',
      json: {
        tasks: tasks
          .filter(task => !task.completed)
          .map(task => ({ id: task.id, list_id: 'atlas', title: task.title, due: task.due })),
        truncated: false,
        failed: [],
      },
    },
    { url: '**/api/v1/workbench/tasks?*', json: { items: tasks, next_page_token: null } },
    { url: '**/api/v1/workbench/contacts?*', json: { items: contacts, next_page_token: null } },
    {
      url: '**/api/v1/workbench/contacts',
      json: { items: contacts, next_page_token: null, truncated: false },
    },
    { url: '**/api/v1/workbench/contacts/contact?*', json: contacts[0] },
    {
      url: '**/api/v1/workbench/contacts/member-of?*',
      json: { groups: [{ id: 'atlas', name: 'Project Atlas', count: 4, own: true }] },
    },
    {
      url: '**/api/v1/workbench/contacts/history?*',
      json: {
        mail: 'used',
        received: [{ id: 'capture-mail-0', subject: MAIL_SUBJECT, at: '2026-10-12T07:10:00Z' }],
        sent: [],
        calendar: 'empty',
        organized_by_them: [],
        organized_by_you: [],
        shared: [],
        meetings_window_days: 720,
        meetings_cut: false,
        telephony: 'empty',
        calls: [],
        calls_window: 500,
        calls_cut: false,
        sms: 'empty',
        texts: [],
        texts_window: 2000,
        texts_cut: false,
      },
    },
    {
      url: '**/api/v1/workbench/contacts/groups',
      json: {
        groups: [
          { id: 'atlas', name: 'Project Atlas', count: 4, own: true },
          { id: 'photo', name: 'Photography club', count: 3, own: true },
        ],
        truncated: false,
      },
    },
    { url: '**/api/v1/workbench/files?*', json: { items: files, next_page_token: null } },
    { url: '**/api/v1/workbench/files', json: { items: files, next_page_token: null } },
    { url: '**/api/v1/workbench/files/quota', json: { used: 2400000000, total: 15000000000 } },
    { url: '**/api/v1/workbench/files/file?*', json: budgetFile },
    {
      url: '**/api/v1/workbench/files/preview?*',
      json: {
        sheets: [
          {
            name: 'Launch budget',
            cut: false,
            rows: [
              ['Item', 'Owner', 'Estimate (EUR)', 'Status'],
              ['Design and prototype', 'Sam Demo', '1800', 'Approved'],
              ['Supplier delivery', 'Morgan Demo', '1500', 'Date to confirm'],
              ['Photography workshop', 'Alex Demo', '600', 'Reserved'],
              ['Accessibility review', 'Sam Demo', '450', 'Complete'],
              ['Contingency', 'Alex Demo', '450', 'Available'],
              ['Total', '', '4800', 'Review on Monday'],
            ],
          },
        ],
      },
    },
    { url: '**/api/v1/workbench/lights', json: lights },
  ];
}
