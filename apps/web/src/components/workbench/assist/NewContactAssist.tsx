'use client';

/**
 * NewContactAssist — « Write with LIA » on a new contact (ADR-372, owner 2026-11-07).
 *
 * One icon in the editor's title line, two ways: the person describes the contact in a sentence,
 * typed or dictated, or a business card is read from a new photo or the photo library.
 * Either fills the form under their eyes: nothing exists until they save it, and what was
 * read is only what the sentence or the card says (the server holds every value to it). What it
 * cost stands in a toast, the form keeping all its room.
 */
import { Camera, ImageIcon, PenLine } from '@/lib/icons';
import { useRef, useState, type ChangeEvent } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useAssistCall } from '@/hooks/useAssistCall';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { ASSIST_PATHS, type CardAnswer, type ProposedContact } from '@/lib/workbench/assist';

import { useAssistBounds } from '../WorkbenchShell';
import { AssistStars } from '@/components/selection-assist/AssistStars';
import { CancelButton, ToolActions, ToolDialogHeader } from '../ToolForm';
import { SentenceDialog } from './SentenceAssist';
import { WaitOrRefusal } from './WritingAssist';
import { tellCost } from './tellings';

const BYTES_PER_MEGABYTE = 1024 * 1024;

export interface NewContactAssistProps {
  lng: Language;
  /** The published ceiling of a picture. */
  maxBytes: number;
  onRead: (card: ProposedContact) => void;
}

/** A business card read from a picture: refused past its ceiling before anything leaves. */
function CardReadingDialog({
  lng,
  maxBytes,
  onRead,
  onClose,
  returnFocus,
}: NewContactAssistProps & { onClose: () => void; returnFocus: () => void }) {
  const { t } = useTranslation(lng);
  const camera = useRef<HTMLInputElement>(null);
  const library = useRef<HTMLInputElement>(null);
  const call = useAssistCall<CardAnswer>();
  const busy = call.state.status === 'running';
  const leave = () => {
    call.stop();
    onClose();
  };

  const picked = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    // Emptied at once: the same picture picked again is a new choice, not no change.
    event.target.value = '';
    if (!file) return;
    if (file.size > maxBytes) {
      toast.error(
        t('workbench.errors.too_large_bounded', {
          megabytes: Number((maxBytes / BYTES_PER_MEGABYTE).toFixed(1)),
        })
      );
      return;
    }
    const form = new FormData();
    form.append('file', file);
    const answer = await call.run(ASSIST_PATHS.contactFromCard, form);
    if (!answer) return;
    tellCost(answer.usage);
    onRead(answer.contact);
    leave();
  };

  return (
    <Dialog open onOpenChange={next => !next && leave()}>
      <DialogContent
        aria-describedby={undefined}
        className="sm:max-w-lg"
        onCloseAutoFocus={event => {
          event.preventDefault();
          returnFocus();
        }}
      >
        <ToolDialogHeader>
          <DialogTitle>{t('workbench.assist.contacts.from_card')}</DialogTitle>
        </ToolDialogHeader>
        <input
          ref={camera}
          type="file"
          accept="image/*"
          capture="environment"
          className="sr-only"
          tabIndex={-1}
          aria-hidden="true"
          onChange={event => void picked(event)}
        />
        <input
          ref={library}
          type="file"
          accept="image/*"
          className="sr-only"
          tabIndex={-1}
          aria-hidden="true"
          onChange={event => void picked(event)}
        />
        <div className="grid gap-3">
          <Button
            type="button"
            variant="outline"
            className="h-auto min-h-11 whitespace-normal"
            disabled={busy}
            onClick={() => camera.current?.click()}
          >
            <Camera className="mr-2 h-4 w-4" aria-hidden="true" />
            {t('workbench.assist.contacts.take_photo')}
          </Button>
          <Button
            type="button"
            variant="outline"
            className="h-auto min-h-11 whitespace-normal"
            disabled={busy}
            onClick={() => library.current?.click()}
          >
            <ImageIcon className="mr-2 h-4 w-4" aria-hidden="true" />
            {t('workbench.assist.contacts.choose_photo')}
          </Button>
        </div>
        <WaitOrRefusal lng={lng} state={call.state} />
        <ToolActions>
          <CancelButton lng={lng} onClick={leave} />
        </ToolActions>
      </DialogContent>
    </Dialog>
  );
}

export function NewContactAssist({ lng, maxBytes, onRead }: NewContactAssistProps) {
  const { t } = useTranslation(lng);
  const bounds = useAssistBounds();
  const trigger = useRef<HTMLButtonElement>(null);
  const [reading, setReading] = useState(false);
  const [describing, setDescribing] = useState(false);
  // Kept between two tries: a refusal or a closing never loses what was said.
  const [words, setWords] = useState('');
  if (!bounds) return null;
  // Its own name: the notes' « Write with LIA » stands in the same form.
  const label = t('workbench.assist.contacts.write');
  const fromWords = t('workbench.assist.contacts.from_words');

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            ref={trigger}
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0"
            aria-label={label}
            title={label}
          >
            <AssistStars className="h-4 w-4" aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem className="gap-2" onSelect={() => setDescribing(true)}>
            <PenLine className="h-4 w-4 shrink-0" aria-hidden="true" />
            {fromWords}
          </DropdownMenuItem>
          <DropdownMenuItem className="gap-2" onSelect={() => setReading(true)}>
            <Camera className="h-4 w-4 shrink-0" aria-hidden="true" />
            {t('workbench.assist.contacts.from_card')}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      {reading && (
        <CardReadingDialog
          lng={lng}
          maxBytes={maxBytes}
          onRead={onRead}
          onClose={() => setReading(false)}
          returnFocus={() => trigger.current?.focus()}
        />
      )}
      {describing && (
        <SentenceDialog<CardAnswer>
          lng={lng}
          label={fromWords}
          path={ASSIST_PATHS.contactFromWords}
          maxInstruction={bounds.instructionMax}
          words={words}
          onWords={setWords}
          onAnswer={answer => {
            tellCost(answer.usage);
            onRead(answer.contact);
          }}
          onClose={() => setDescribing(false)}
        />
      )}
    </>
  );
}
