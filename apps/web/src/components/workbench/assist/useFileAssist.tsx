'use client';

/**
 * What LIA can do on an open file (ADR-372): the list under its bar's last icon, and the answer's
 * place in the detail. The server reads the file by what it is: nothing runs until a line is pressed.
 * It can leave in a message written with LIA (2026-11-07), attached as « Send by mail » attaches it,
 * under the same bound, the message opening on « Write from an instruction ».
 */
import { PenLine } from '@/lib/icons';
import type { ReactNode } from 'react';

import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { ASSIST_PATHS, type TextAnswer } from '@/lib/workbench/assist';
import { isTooLarge } from '@/lib/workbench/files';
import { driveAttachment } from '@/lib/workbench/mail-compose';
import type { WorkbenchFileDetail } from '@/lib/workbench/types';

import type { AssistOffer, DetailDeed } from '../DetailBar';
import { useToolBridges } from '../useToolBridges';
import { AssistPanel, ReadWords } from './AssistPanel';
import { confideLine, keepLine, readLine, readyLine, remindLine } from './lines';
import { useAssistCall } from '@/hooks/useAssistCall';

export interface FileAssist extends AssistOffer {
  /** The answer, where the detail draws it. */
  panel: ReactNode;
}

/**
 * @param lng - The reader's language.
 * @param file - The file read, once it is.
 * @param mailMax - The bound a file leaves by mail under; without it, it leaves by no message.
 * @returns The offer of its bar and the answer's place; nothing while it is being read.
 */
export function useFileAssist(
  lng: Language,
  file: WorkbenchFileDetail | undefined,
  mailMax?: number
): FileAssist {
  const { t } = useTranslation(lng);
  const { ask, remind, confide, keep, assists, offers, go } = useToolBridges(lng);
  const summary = useAssistCall<TextAnswer>(file?.id ?? null);
  if (!file) return { lines: [], panel: null };
  const name = file.name || t('workbench.files.no_name');
  const read = () => void summary.run(ASSIST_PATHS.fileSummary, { file_id: file.id });
  const leaves =
    assists &&
    mailMax !== undefined &&
    file.downloadable &&
    !isTooLarge(file, mailMax) &&
    offers('compose');
  const mails: DetailDeed[] = leaves
    ? [
        {
          label: t('workbench.assist.file.mail_with_lia'),
          icon: PenLine,
          onSelect: () =>
            go({ kind: 'compose', to: '', file: driveAttachment(file), assisted: true }),
        },
      ]
    : [];
  return {
    lines: [
      ...(assists && file.previewable ? [readLine(t, file.mime_type, read)] : []),
      ...mails,
      remindLine(t, t('workbench.assist.remind.words.file', { name }), remind),
      ...(file.downloadable ? keepLine(t, { kind: 'file', name, file_id: file.id }, keep) : []),
      ...confideLine(t, name, t('workbench.assist.confide.brief_file', { name }), confide),
      readyLine(t, 'file', { name }, ask),
    ],
    busy: summary.state.status === 'running',
    panel: (
      <AssistPanel lng={lng} title={t('workbench.assist.file.summary_title')} call={summary}>
        {answer => (
          <ReadWords
            text={answer.text}
            cutNote={answer.cut ? t('workbench.assist.file.cut') : null}
          />
        )}
      </AssistPanel>
    ),
  };
}
