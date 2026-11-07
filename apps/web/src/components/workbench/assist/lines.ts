/**
 * The lines every tool's question to LIA holds (ADR-372): one list under one icon, so a screen with
 * little room gains no control.
 *
 * What LIA can do here comes first, what is left for later next, what goes to the chat last, each
 * group set apart. A ready-made question is words the person reads in the chat before sending them:
 * it runs nothing by itself, and costs nothing until they send it.
 */
import { Bell, Bot, Library, MessageCircleQuestion, ScrollText } from 'lucide-react';

import type { DetailDeed } from '../DetailBar';
import type { Keeping } from './KeepDialog';
import type { AssistDoors } from './useAssistHost';

/** Words in the reader's language. */
export type Say = (key: string, values?: Record<string, string | number>) => string;

/** Each thing a ready-made question exists for. */
export type ReadyQuestion = 'mail' | 'event' | 'task' | 'contact' | 'file' | 'lights';

/** @returns The line where it applies; nothing elsewhere. */
export function lineIf(condition: boolean, line: DetailDeed): readonly DetailDeed[] {
  return condition ? [line] : [];
}

/** « Remind me » on these words: it opens the section's one dialog. */
export function remindLine(t: Say, words: string, remind: (words: string) => void): DetailDeed {
  return {
    label: t('workbench.assist.remind.line'),
    icon: Bell,
    ruled: true,
    onSelect: () => remind(words),
  };
}

/** Hands the thing to LIA as a ticket; nothing where the board is off. */
export function confideLine(
  t: Say,
  title: string,
  brief: string,
  confide: AssistDoors['confide']
): readonly DetailDeed[] {
  if (!confide) return [];
  return [
    {
      label: t('workbench.assist.confide.line'),
      icon: Bot,
      onSelect: () => confide({ title, brief }),
    },
  ];
}

/** Keeps a file in a knowledge space; nothing where spaces are off. */
export function keepLine(t: Say, what: Keeping, keep: AssistDoors['keep']): readonly DetailDeed[] {
  if (!keep) return [];
  return [{ label: t('workbench.assist.keep.line'), icon: Library, onSelect: () => keep(what) }];
}

/** Reading a file: an image is described, anything else summed up. */
export function readLine(t: Say, mimeType: string, onSelect: () => void): DetailDeed {
  const image = mimeType.startsWith('image/');
  return {
    label: t(image ? 'workbench.assist.file.describe' : 'workbench.assist.file.summary'),
    icon: ScrollText,
    onSelect,
  };
}

/** The ready-made question of a thing, handed to the chat unsent. */
export function readyLine(
  t: Say,
  thing: ReadyQuestion,
  values: Record<string, string>,
  ask: (words: string) => void
): DetailDeed {
  return {
    label: t(`workbench.ask.ready.${thing}`),
    icon: MessageCircleQuestion,
    asks: true,
    ruled: true,
    onSelect: () => ask(t(`workbench.ask.ready.${thing}_words`, values)),
  };
}
