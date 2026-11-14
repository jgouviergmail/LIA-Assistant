'use client';

/**
 * The dialogs every tool can open (ADR-372), held once for the section.
 *
 * What is left for later (`remind`), handed to LIA (`confide`) or kept (`keep`) is the person's own
 * act and calls no model. A door that leads nowhere on this instance is simply absent.
 */
import { useState, type ReactNode } from 'react';

import { useAuth } from '@/hooks/useAuth';
import type { AppConfig } from '@/hooks/useAppConfig';
import { canRecordVoice } from '@/hooks/useVoiceInput';
import type { Language } from '@/i18n/settings';
import { capabilityEnabled } from '@/lib/capability-state';
import { meetingsAvailable } from '@/lib/meetings/availability';
import { ragSpacesAvailable } from '@/lib/rag-spaces/availability';
import { workboardAvailable } from '@/lib/workboard/availability';
import { toolAssistsAvailable } from '@/lib/workbench/availability';

import { ConfideDialog, type Confiding } from './ConfideDialog';
import { KeepDialog, type Keeping } from './KeepDialog';
import { ReminderDialog } from './ReminderDialog';

export interface AssistDoors {
  /** Opens « Remind me » on these words. */
  remind: (words: string) => void;
  /** Hands the thing to LIA as a ticket; left out where the board is off. */
  confide?: (what: Confiding) => void;
  /** Keeps the file in a space; left out where spaces or the assists' routes are off. */
  keep?: (what: Keeping) => void;
  /** An event's minutes can be read, and a meeting recorded. */
  meetings: boolean;
  /** Words can be said into a field. */
  dictates: boolean;
  /** Words on the screen can be read aloud. */
  reads: boolean;
}

export interface AssistHost {
  doors: AssistDoors;
  dialogs: ReactNode;
}

/** What this instance leaves open: the operator's switch, then the deployment's ceiling. */
function openings(config: AppConfig | null) {
  const capabilities = config?.capabilities;
  return {
    board: workboardAvailable(config),
    spaces: ragSpacesAvailable(config) && toolAssistsAvailable(config),
    meetings: meetingsAvailable(config),
    dictates: capabilityEnabled(capabilities, 'stt', undefined) && canRecordVoice(),
    reads: capabilityEnabled(capabilities, 'tts', undefined),
  };
}

/**
 * @param lng - The reader's language.
 * @param config - The app's configuration, once read.
 * @returns The doors, and their dialogs for the shell to draw.
 */
export function useAssistHost(lng: Language, config: AppConfig | null): AssistHost {
  const { user } = useAuth();
  const [reminding, setReminding] = useState<string | null>(null);
  const [confiding, setConfiding] = useState<Confiding | null>(null);
  const [keeping, setKeeping] = useState<Keeping | null>(null);
  const { board, spaces, meetings, dictates, reads } = openings(config);
  return {
    doors: {
      remind: setReminding,
      confide: board ? setConfiding : undefined,
      keep: spaces ? setKeeping : undefined,
      meetings,
      dictates,
      reads,
    },
    dialogs: (
      <>
        {reminding !== null && (
          <ReminderDialog
            lng={lng}
            words={reminding}
            zone={user?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone}
            onClose={() => setReminding(null)}
          />
        )}
        {confiding && <ConfideDialog lng={lng} {...confiding} onClose={() => setConfiding(null)} />}
        {keeping && <KeepDialog lng={lng} what={keeping} onClose={() => setKeeping(null)} />}
      </>
    ),
  };
}
