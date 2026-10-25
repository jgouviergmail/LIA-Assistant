'use client';

/**
 * Import a meeting from a file (owner request 2026-10-24).
 *
 * A WAV, MP3 or M4A — a phone's voice memo, a recorder's file — becomes a
 * meeting like a recording: checked against the bounds the server publishes
 * (read when the dialog opens), dated by default when it began, sent in chunks
 * under a progress bar, then handed to processing — and the meeting's page
 * opens on its progress. Closing while it travels stops the upload and deletes
 * what was sent: an import is all or nothing.
 */

import { useEffect, useId, useRef, useState } from 'react';
import { FileAudio, Loader2, Upload } from 'lucide-react';

import { TemplateSelect } from '@/components/meetings/TemplateSelect';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { useMeetingTemplates } from '@/hooks/useMeetingTemplates';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { formatFileSize } from '@/lib/format';
import { MEETING_IMPORT_LIMITS_PATH, meetingErrorCode, meetingsApi } from '@/lib/meetings/api';
import { formatElapsed, MEETING_LANGUAGE_HINTS } from '@/lib/meetings/format';
import {
  defaultRecordedAt,
  fromLocalInput,
  IMPORT_ACCEPT,
  importFormatOf,
  importRefusal,
  readAudioDuration,
  toLocalInput,
} from '@/lib/meetings/import-file';
import { uploadImportFile } from '@/lib/meetings/import-uploader';
import type { MeetingImportLimits } from '@/types/meetings';

interface MeetingImportDialogProps {
  lng: Language;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface Chosen {
  file: File;
  /** As the browser read it; null when it could not (the server measures anyway). */
  duration: number | null;
}

interface Progress {
  sent: number;
  total: number;
}

/** The chosen file, its length read in the background, its date edited or not. */
function useChosenFile() {
  const [chosen, setChosen] = useState<Chosen | null>(null);
  const [recordedAt, setRecordedAt] = useState('');
  const edited = useRef(false);
  const choose = (file: File | null) => {
    edited.current = false;
    setChosen(file ? { file, duration: null } : null);
    if (!file) return;
    setRecordedAt(toLocalInput(defaultRecordedAt(file.lastModified, null)));
    void readAudioDuration(file).then(duration => {
      setChosen(current => (current?.file === file ? { file, duration } : current));
      // Only while the person has not set the date themselves.
      if (!edited.current)
        setRecordedAt(toLocalInput(defaultRecordedAt(file.lastModified, duration)));
    });
  };
  const editDate = (value: string) => {
    edited.current = true;
    setRecordedAt(value);
  };
  return { chosen, choose, recordedAt, editDate };
}

function ChosenSummary({ lng, chosen }: { lng: Language; chosen: Chosen }) {
  const { t } = useTranslation(lng);
  const parts = [chosen.file.name, formatFileSize(chosen.file.size)];
  if (chosen.duration !== null) parts.push(formatElapsed(chosen.duration));
  return (
    <p className="flex min-w-0 items-center gap-2 text-sm text-muted-foreground">
      <FileAudio className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
      <span className="min-w-0 [overflow-wrap:anywhere]">
        {t('meetings.import.summary', { details: parts.join(' · ') })}
      </span>
    </p>
  );
}

function UploadProgress({ lng, progress }: { lng: Language; progress: Progress }) {
  const { t } = useTranslation(lng);
  const percent = progress.total ? Math.round((progress.sent / progress.total) * 100) : 0;
  return (
    <div className="space-y-2">
      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        aria-label={t('meetings.import.progress_label')}
        className="h-2 w-full overflow-hidden rounded-full bg-muted"
      >
        <div className="h-full bg-primary transition-all" style={{ width: `${percent}%` }} />
      </div>
      <p className="text-xs text-muted-foreground" aria-live="polite">
        {t('meetings.import.sending', { sent: progress.sent, total: progress.total })}
      </p>
    </div>
  );
}

function refusalText(
  t: (key: string, options?: Record<string, unknown>) => string,
  limits: MeetingImportLimits,
  refusal: string
): string {
  return t(`meetings.import.refusal_${refusal}`, {
    size: formatFileSize(limits.max_bytes),
    minutes: limits.max_duration_minutes,
  });
}

function ImportForm({
  lng,
  limits,
  onClose,
}: {
  lng: Language;
  limits: MeetingImportLimits;
  onClose: () => void;
}) {
  const { t } = useTranslation(lng);
  const id = useId();
  const router = useLocalizedRouter();
  const { templates } = useMeetingTemplates(true);
  const { chosen, choose, recordedAt, editDate } = useChosenFile();
  const [language, setLanguage] = useState('auto');
  const [templateRef, setTemplateRef] = useState<string | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  // Closing mid-upload is a cancel: nothing keeps travelling behind a closed dialog.
  useEffect(() => () => abort.current?.abort(), []);

  const refusal = chosen ? importRefusal(chosen.file, chosen.duration, limits) : null;
  const format = chosen ? importFormatOf(chosen.file) : null;
  const sending = progress !== null;

  const submit = async () => {
    if (!chosen || !format || refusal || sending) return;
    // Created BEFORE the first call: closing while the import opens stops it too.
    const controller = new AbortController();
    abort.current = controller;
    setError(null);
    setProgress({ sent: 0, total: 1 });
    try {
      const started = await meetingsApi.startImport({
        audio_format: format,
        size_bytes: chosen.file.size,
        recorded_at: (
          fromLocalInput(recordedAt) ?? new Date(chosen.file.lastModified)
        ).toISOString(),
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        language,
        template_ref: templateRef,
      });
      const result = await uploadImportFile({
        meetingId: started.id,
        file: chosen.file,
        chunkBytes: started.limits.chunk_max_bytes,
        signal: controller.signal,
        onProgress: (sent, total) => setProgress({ sent, total }),
      });
      if (result.kind === 'complete') {
        onClose();
        router.push(`/dashboard/meetings/${started.id}`);
        return;
      }
      // Part of a file is no meeting: what was sent goes with the import.
      void meetingsApi.remove(started.id).catch(() => undefined);
      if (result.kind === 'refused') setError(result.code);
    } catch (failure) {
      setError(meetingErrorCode(failure) ?? 'unexpected');
    }
    setProgress(null);
  };

  const cancel = () => {
    abort.current?.abort();
    onClose();
  };

  return (
    <>
      <div className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor={`${id}-file`}>{t('meetings.import.file_label')}</Label>
          <Input
            id={`${id}-file`}
            type="file"
            accept={IMPORT_ACCEPT}
            disabled={sending}
            aria-describedby={`${id}-bounds`}
            onChange={event => choose(event.target.files?.[0] ?? null)}
          />
          <p id={`${id}-bounds`} className="text-xs text-muted-foreground">
            {t('meetings.import.bounds', {
              size: formatFileSize(limits.max_bytes),
              minutes: limits.max_duration_minutes,
            })}
          </p>
          {chosen && <ChosenSummary lng={lng} chosen={chosen} />}
          {refusal && (
            <p role="alert" className="text-sm text-destructive">
              {refusalText(t, limits, refusal)}
            </p>
          )}
        </div>
        <div className="space-y-2">
          <Label htmlFor={`${id}-date`}>{t('meetings.import.recorded_at_label')}</Label>
          <Input
            id={`${id}-date`}
            type="datetime-local"
            value={recordedAt}
            max={toLocalInput(new Date())}
            disabled={sending || !chosen}
            aria-describedby={`${id}-date-hint`}
            onChange={event => editDate(event.target.value)}
          />
          <p id={`${id}-date-hint`} className="text-xs text-muted-foreground">
            {t('meetings.import.recorded_at_hint')}
          </p>
        </div>
        <TemplateSelect
          lng={lng}
          id={`${id}-template`}
          label={t('meetings.import.template_label')}
          templates={templates}
          value={templateRef}
          onChange={setTemplateRef}
          autoLabel={t('meetings.import.template_default')}
        />
        <div className="space-y-2">
          <Label htmlFor={`${id}-language`}>{t('meetings.settings.language_label')}</Label>
          <Select value={language} onValueChange={setLanguage} disabled={sending}>
            <SelectTrigger id={`${id}-language`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="auto">{t('meetings.settings.language_auto')}</SelectItem>
              {MEETING_LANGUAGE_HINTS.map(code => (
                <SelectItem key={code} value={code}>
                  {t(`meetings.settings.language_codes.${code}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {progress && <UploadProgress lng={lng} progress={progress} />}
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {t(`meetings.errors.${error}`, {
              defaultValue: t('meetings.errors.unknown', { code: error }),
            })}
          </p>
        )}
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={cancel}>
          {t('common.cancel')}
        </Button>
        <Button
          onClick={() => void submit()}
          aria-disabled={!chosen || refusal !== null || sending}
        >
          {sending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <Upload className="mr-2 h-4 w-4" aria-hidden="true" />
          )}
          {t('meetings.import.submit')}
        </Button>
      </DialogFooter>
    </>
  );
}

function ImportBody({ lng, onClose }: { lng: Language; onClose: () => void }) {
  const { t } = useTranslation(lng);
  const limits = useApiQuery<MeetingImportLimits>(MEETING_IMPORT_LIMITS_PATH, {
    componentName: 'MeetingImportDialog',
  });
  if (limits.data) return <ImportForm lng={lng} limits={limits.data} onClose={onClose} />;
  if (limits.error) {
    const code = meetingErrorCode(limits.error) ?? 'unexpected';
    return (
      <p role="alert" className="text-sm text-destructive">
        {t(`meetings.errors.${code}`, {
          defaultValue: t('meetings.errors.unknown', { code }),
        })}
      </p>
    );
  }
  return (
    <div className="flex justify-center py-8">
      <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-hidden="true" />
      <span className="sr-only">{t('meetings.import.loading')}</span>
    </div>
  );
}

export function MeetingImportDialog({ lng, open, onOpenChange }: MeetingImportDialogProps) {
  const { t } = useTranslation(lng);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Upload className="h-4 w-4 text-primary" aria-hidden="true" />
            {t('meetings.import.title')}
          </DialogTitle>
          <DialogDescription>{t('meetings.import.description')}</DialogDescription>
        </DialogHeader>
        {open && <ImportBody lng={lng} onClose={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  );
}
