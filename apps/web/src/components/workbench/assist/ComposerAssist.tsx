'use client';

/**
 * ComposerAssist — writing a message with LIA (ADR-372): the lines a composer offers, at the end of
 * the label of the field they write (owner, 2026-11-06).
 *
 * What is offered follows what stands in the composer. Under the message: the answer to a message,
 * a message from an instruction, then, once words are written, their changes and their translation.
 * Under the subject: a subject for those words, or before any the same message from an instruction,
 * which writes both.
 */
import { Heading, MessageSquareReply, PenLine } from '@/lib/icons';

import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { ASSIST_PATHS, type TextAnswer } from '@/lib/workbench/assist';
import { ownWords, type ComposerFields, type ComposerTarget } from '@/lib/workbench/mail-compose';
import type { MailMessage } from '@/lib/workbench/types';

import { useAssistBounds } from '../WorkbenchShell';
import type { Say } from './lines';
import { rewriteLines, translateLine } from './writingLines';
import { WritingAssist, type WritingLine, type WritingUse } from './WritingAssist';

const REPLY_LINE = 'reply';
const SUBJECT_LINE = 'subject';
const COMPOSE_LINE = 'compose';

function replyLine(message: MailMessage, t: Say): WritingLine {
  return {
    key: REPLY_LINE,
    label: t('workbench.assist.mail.reply'),
    icon: MessageSquareReply,
    path: ASSIST_PATHS.mailReply,
    body: instruction => ({ message_id: message.id, instruction }),
    instruction: 'optional',
    suggestions: [
      t('workbench.assist.writing.accept'),
      t('workbench.assist.writing.decline'),
      t('workbench.assist.writing.delay'),
    ],
  };
}

function composeLine(recipient: string, t: Say): WritingLine {
  return {
    key: COMPOSE_LINE,
    label: t('workbench.assist.writing.compose'),
    icon: PenLine,
    path: ASSIST_PATHS.mailCompose,
    body: instruction => ({ instruction, recipient: recipient || null }),
    instruction: 'required',
  };
}

function subjectLine(body: string, recipient: string, t: Say): WritingLine {
  return {
    key: SUBJECT_LINE,
    label: t('workbench.assist.writing.subject'),
    icon: Heading,
    path: ASSIST_PATHS.mailSubject,
    body: () => ({ body, recipient: recipient || null }),
    whole: true,
  };
}

export interface ComposerAssistProps {
  lng: Language;
  /** The field it stands beside. */
  field: 'subject' | 'body';
  target: ComposerTarget;
  fields: ComposerFields;
  /** What a body gains to carry the person's signature. */
  signature: string;
  /** The person writes a subject here: an answer's is its message's. */
  writesSubject: boolean;
  /** LIA's words joined the body, with the subject they came with, if any. */
  onBody: (answer: TextAnswer, use: WritingUse) => void;
  onSubject: (subject: string) => void;
}

/** @returns What the message's own words can become, for the field the person is at. */
function linesOf(
  field: ComposerAssistProps['field'],
  {
    target,
    fields,
    writesSubject,
  }: Pick<ComposerAssistProps, 'target' | 'fields' | 'writesSubject'>,
  own: string,
  readable: boolean,
  lng: Language,
  t: Say
): readonly WritingLine[] {
  const compose = target.kind !== 'reply' && !own ? [composeLine(fields.to, t)] : [];
  if (field === 'subject') {
    return readable && writesSubject ? [subjectLine(own, fields.to, t)] : compose;
  }
  return [
    ...(target.kind === 'reply' ? [replyLine(target.message, t)] : []),
    ...compose,
    ...(readable ? rewriteLines(t, own) : []),
    ...(readable ? [translateLine(t, lng, own)] : []),
  ];
}

/** The line the message opens on, asked for elsewhere: an answer's proposal, or a whole message. */
function openedOn(field: ComposerAssistProps['field'], target: ComposerTarget): string | null {
  if (field !== 'body') return null;
  if (target.kind === 'reply' && target.propose) return REPLY_LINE;
  if (target.kind === 'new' && target.assisted) return COMPOSE_LINE;
  return null;
}

/** Words said into the field the person is at: after the message's words, or the subject's. */
function dictated(
  props: Pick<ComposerAssistProps, 'field' | 'fields' | 'writesSubject' | 'onBody' | 'onSubject'>
): ((words: string) => void) | undefined {
  const { field, fields, writesSubject, onBody, onSubject } = props;
  if (field === 'body') {
    return words => onBody({ text: words, subject: null, cut: false, usage: null }, 'add');
  }
  if (!writesSubject) return undefined;
  return words => onSubject([fields.subject.trimEnd(), words].filter(Boolean).join(' '));
}

export function ComposerAssist(props: ComposerAssistProps) {
  const { lng, field, target, fields, signature, writesSubject, onBody, onSubject } = props;
  const { t } = useTranslation(lng);
  const bounds = useAssistBounds();
  if (!bounds) return null;
  const own = ownWords(fields, signature).trim();
  const readable = own !== '' && own.length <= bounds.textMax;
  return (
    <WritingAssist
      lng={lng}
      compact
      lines={linesOf(field, { target, fields, writesSubject }, own, readable, lng, t)}
      blank={!own}
      maxInstruction={bounds.instructionMax}
      onApply={(answer, use, line) => {
        if (line.key === SUBJECT_LINE) onSubject(answer.text);
        else onBody(answer, use);
      }}
      startWith={openedOn(field, target)}
      onDictated={bounds.dictates ? dictated(props) : undefined}
    />
  );
}
