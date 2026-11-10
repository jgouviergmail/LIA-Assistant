'use client';

/**
 * What LIA can do on an open message (ADR-372): the list under the reader's last icon, and the
 * answer's place in the reader. Nothing runs until a line is pressed.
 */
import {
  CalendarPlus,
  Eye,
  Languages,
  ListPlus,
  MessagesSquare,
  MessageSquareReply,
  ScrollText,
  Volume2,
} from '@/lib/icons';
import { useState, type ReactNode } from 'react';

import { useMailWatch } from '@/hooks/useMailWatch';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { canWatch } from '@/lib/mail-watch';
import {
  ASSIST_PATHS,
  type EventAnswer,
  type MailSummaryAnswer,
  type ProposedEvent,
  type ProposedTask,
  type ReadAloudAnswer,
  type TaskAnswer,
  type TextAnswer,
} from '@/lib/workbench/assist';
import { addressLabel, receivedFull } from '@/lib/workbench/mail';
import type { MailAttachment, MailMessage } from '@/lib/workbench/types';

import type { AssistOffer, DetailDeed } from '../DetailBar';
import { useToolBridges, type ToolBridges } from '../useToolBridges';
import { useAssistBounds, type AssistBounds } from '../WorkbenchShell';
import { AssistPanel, HeardWords, ReadWords, VoiceCost } from './AssistPanel';
import { confideLine, keepLine, lineIf, readLine, readyLine, remindLine, type Say } from './lines';
import { MailSummaryView } from './MailSummaryView';
import { tellCost } from './tellings';
import { useAssistCall, type AssistCall } from '@/hooks/useAssistCall';

export interface MailAssist extends AssistOffer {
  /** The answer, where the reader draws it. */
  panel: ReactNode;
  /** What LIA can do on one of its files, shown as the person reads its name. */
  attachmentLines: (attachment: MailAttachment, name: string) => readonly DetailDeed[];
}

export interface MailAssistDoors {
  /** Opens the answer to the message with a proposal on its way. */
  onPropose: (message: MailMessage) => void;
  /** Opens the form of the task LIA read in the message; left out without a tasks tool. */
  onTask?: (message: MailMessage, task: ProposedTask) => void;
  /** The names of the person's task lists, which the message is read against. */
  taskLists?: () => Promise<string[]>;
  /** Opens the editor on the event it describes; left out without a calendar. */
  onEvent?: (message: MailMessage, event: ProposedEvent) => void;
  /** It is read among what the person sent: its answer comes from whom it went to. */
  sent?: boolean;
  /** How many messages its conversation shows: one alone has nothing to sum up. */
  said?: number;
  /** The account's zone: the day and hour a ticket names are the ones the reader reads. */
  zone?: string;
}

/** Every call a message can be the subject of, one panel each. */
interface MailCalls {
  summary: AssistCall<MailSummaryAnswer>;
  translation: AssistCall<TextAnswer>;
  conversation: AssistCall<TextAnswer>;
  attachment: AssistCall<TextAnswer>;
  heard: AssistCall<ReadAloudAnswer>;
  event: AssistCall<EventAnswer>;
  task: AssistCall<TaskAnswer>;
}

function useMailCalls(scope: string | null): MailCalls {
  return {
    summary: useAssistCall<MailSummaryAnswer>(scope),
    translation: useAssistCall<TextAnswer>(scope),
    conversation: useAssistCall<TextAnswer>(scope),
    attachment: useAssistCall<TextAnswer>(scope),
    heard: useAssistCall<ReadAloudAnswer>(scope),
    event: useAssistCall<EventAnswer>(scope),
    task: useAssistCall<TaskAnswer>(scope),
  };
}

/** What a line of this message needs. */
interface MailContext {
  t: Say;
  lng: Language;
  message: MailMessage;
  calls: MailCalls;
  doors: MailAssistDoors;
  /** Stops whatever is on its way: one answer at a time. */
  quiet: () => void;
}

/** A line that asks about the message and answers in its panel. */
function askedLine(
  { message, quiet }: MailContext,
  label: string,
  icon: DetailDeed['icon'],
  call: Pick<AssistCall<TextAnswer | MailSummaryAnswer>, 'run'>,
  path: string
): DetailDeed {
  return {
    label,
    icon,
    onSelect: () => {
      quiet();
      void call.run(path, { message_id: message.id });
    },
  };
}

function readAloudLine(context: MailContext, bounds: AssistBounds): DetailDeed {
  const { t, message, calls, quiet } = context;
  return {
    label: t('workbench.assist.voice.read'),
    icon: Volume2,
    onSelect: () => {
      quiet();
      void calls.heard.run(ASSIST_PATHS.readAloud, {
        text: message.body.slice(0, bounds.textMax),
      });
    },
  };
}

/**
 * The task the message leaves, or the one an act it names asks for, read against the person's
 * lists; its form opens elsewhere, so the cost is said here.
 *
 * @param focus - The act chosen (a line of its summary): the task read is that one.
 */
async function askTask({ message, calls, doors }: MailContext, focus?: string): Promise<void> {
  const lists = (await doors.taskLists?.()) ?? [];
  const answer = await calls.task.run(ASSIST_PATHS.mailTask, {
    message_id: message.id,
    lists,
    ...(focus ? { focus } : {}),
  });
  if (!answer) return;
  tellCost(answer.usage);
  doors.onTask?.(message, answer.task);
}

/**
 * The event the message describes; its editor opens elsewhere, so the cost is said here.
 */
async function askEvent({ message, calls, doors }: MailContext): Promise<void> {
  const answer = await calls.event.run(ASSIST_PATHS.mailEvent, {
    message_id: message.id,
  });
  if (!answer) return;
  tellCost(answer.usage);
  doors.onEvent?.(message, answer.event);
}

/** What an extraction opens: the cost is said here, its page going on elsewhere. */
function formLines(context: MailContext): readonly DetailDeed[] {
  const { t, doors, quiet } = context;
  const { onEvent, onTask } = doors;
  const toEvent = async () => {
    quiet();
    await askEvent(context);
  };
  const toTask = async () => {
    quiet();
    await askTask(context);
  };
  return [
    ...lineIf(Boolean(onEvent), {
      label: t('workbench.assist.mail.to_event'),
      icon: CalendarPlus,
      onSelect: () => void toEvent(),
    }),
    ...lineIf(Boolean(onTask), {
      label: t('workbench.assist.mail.to_task_line'),
      icon: ListPlus,
      onSelect: () => void toTask(),
    }),
  ];
}

/** What a model does on the message: none of it where a click may not ask one. */
function modelLines(
  context: MailContext,
  speaks: AssistBounds | null,
  assists: boolean
): readonly DetailDeed[] {
  if (!assists) return [];
  const { t, message, calls, doors } = context;
  const hasWords = message.body.trim() !== '';
  return [
    askedLine(
      context,
      t('workbench.assist.mail.summary'),
      ScrollText,
      calls.summary,
      ASSIST_PATHS.mailSummary
    ),
    ...((doors.said ?? 0) > 1
      ? [
          askedLine(
            context,
            t('workbench.assist.mail.conversation'),
            MessagesSquare,
            calls.conversation,
            ASSIST_PATHS.mailConversation
          ),
        ]
      : []),
    askedLine(
      context,
      t('workbench.assist.mail.translate'),
      Languages,
      calls.translation,
      ASSIST_PATHS.mailTranslate
    ),
    ...(speaks && hasWords ? [readAloudLine(context, speaks)] : []),
    {
      label: t('workbench.assist.mail.reply'),
      icon: MessageSquareReply,
      onSelect: () => doors.onPropose(message),
    },
    ...formLines(context),
  ];
}

/** A watch on whoever the answer would come from; nothing when nobody can be waited for. */
function watchLine(
  { t, message, doors }: MailContext,
  watch: ReturnType<typeof useMailWatch>['watch']
): readonly DetailDeed[] {
  const awaited = doors.sent ? message.to[0] : message.sender;
  if (!awaited) return [];
  const source = { sender_email: awaited.address, sender_name: awaited.name };
  return lineIf(canWatch(source), {
    label: t('workbench.assist.mail.watch'),
    icon: Eye,
    onSelect: () => void watch(source, addressLabel(awaited)),
  });
}

/** What a ticket tells LIA of the mail: whose, which, and when it came, so its run finds that one. */
function mailBrief({ t, lng, message, doors }: MailContext, sender: string, subject: string) {
  const when = receivedFull(message.received_at, doors.zone, lng);
  return when
    ? t('workbench.assist.confide.brief_mail_on', { sender, subject, when })
    : t('workbench.assist.confide.brief_mail', { sender, subject });
}

/** What the person leaves for later, or to someone else. */
function laterLines(
  context: MailContext,
  bridges: ToolBridges,
  watch: ReturnType<typeof useMailWatch>['watch']
): readonly DetailDeed[] {
  const { t, message } = context;
  const sender = message.sender ? addressLabel(message.sender) : '';
  const subject = message.subject || t('workbench.mail.no_subject');
  return [
    remindLine(t, t('workbench.assist.remind.words.mail', { sender, subject }), bridges.remind),
    ...watchLine(context, watch),
    ...confideLine(t, subject, mailBrief(context, sender, subject), bridges.confide),
    readyLine(t, 'mail', { sender, subject }, bridges.ask),
  ];
}

/** Where every answer lands, in the order they are read. */
function MailPanels({
  lng,
  calls,
  attachmentRead,
  onAction,
}: {
  lng: Language;
  calls: MailCalls;
  attachmentRead: string;
  /** Makes a whole task of an action the summary found; left out without a tasks tool. */
  onAction?: (action: string) => void;
}) {
  const { t } = useTranslation(lng);
  const { summary, translation, conversation, heard, attachment, event, task } = calls;
  const read = t('workbench.assist.voice.read');
  return (
    <>
      <AssistPanel lng={lng} title={t('workbench.assist.mail.summary_title')} call={summary}>
        {answer => <MailSummaryView lng={lng} answer={answer} onTask={onAction} />}
      </AssistPanel>
      <AssistPanel
        lng={lng}
        title={t('workbench.assist.mail.translation_title')}
        call={translation}
      >
        {answer => (
          <ReadWords
            text={answer.text}
            cutNote={answer.cut ? t('workbench.assist.mail.translation_cut') : null}
          />
        )}
      </AssistPanel>
      <AssistPanel
        lng={lng}
        title={t('workbench.assist.mail.conversation_title')}
        call={conversation}
      >
        {answer => (
          <ReadWords
            text={answer.text}
            cutNote={answer.cut ? t('workbench.assist.mail.conversation_cut') : null}
          />
        )}
      </AssistPanel>
      <AssistPanel
        lng={lng}
        title={read}
        call={heard}
        spent={answer => <VoiceCost lng={lng} cost={answer.cost_eur} />}
      >
        {answer => <HeardWords lng={lng} label={read} answer={answer} />}
      </AssistPanel>
      <AssistPanel lng={lng} title={attachmentRead} call={attachment}>
        {answer => (
          <ReadWords
            text={answer.text}
            cutNote={answer.cut ? t('workbench.assist.file.cut') : null}
          />
        )}
      </AssistPanel>
      <AssistPanel lng={lng} title={t('workbench.assist.mail.to_event')} call={event}>
        {() => null}
      </AssistPanel>
      <AssistPanel lng={lng} title={t('workbench.assist.mail.to_task_line')} call={task}>
        {() => null}
      </AssistPanel>
    </>
  );
}

/**
 * @param lng - The reader's language.
 * @param message - The message read, once it is.
 * @param doors - Where its answers lead.
 * @returns The offer of its bar, and the answer's place; nothing while it is being read.
 */
export function useMailAssist(
  lng: Language,
  message: MailMessage | undefined,
  doors: MailAssistDoors
): MailAssist {
  const { t } = useTranslation(lng);
  const bridges = useToolBridges(lng);
  const bounds = useAssistBounds();
  const { watch } = useMailWatch();
  const calls = useMailCalls(message?.id ?? null);
  const [attachmentRead, setAttachmentRead] = useState('');
  if (!message) return { lines: [], panel: null, attachmentLines: () => [] };
  const each = Object.values(calls);
  const quiet = () => each.forEach(call => call.stop());
  const context: MailContext = { t, lng, message, calls, doors, quiet };
  const attachmentLines = (file: MailAttachment, name: string): readonly DetailDeed[] => {
    const handle = { message_id: message.id, attachment_id: file.id };
    const read = () => {
      quiet();
      setAttachmentRead(name);
      void calls.attachment.run(ASSIST_PATHS.mailAttachment, {
        ...handle,
        filename: file.filename,
      });
    };
    return [
      ...(bridges.assists && file.previewable ? [readLine(t, file.mime_type, read)] : []),
      ...keepLine(
        t,
        { kind: 'attachment', name, filename: file.filename, ...handle },
        bridges.keep
      ),
    ];
  };
  return {
    lines: [
      ...modelLines(context, bridges.reads ? bounds : null, bridges.assists),
      ...laterLines(context, bridges, watch),
    ],
    busy: each.some(call => call.state.status === 'running'),
    attachmentLines,
    panel: (
      <MailPanels
        lng={lng}
        calls={calls}
        attachmentRead={attachmentRead}
        // The summary stays where it is: only the task's own call starts.
        onAction={doors.onTask && (action => void askTask(context, action))}
      />
    ),
  };
}
