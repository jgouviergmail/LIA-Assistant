'use client';

/**
 * « Change the format » (ADR-259): write the minutes again from the stored
 * transcript with another template — in place, or as new minutes.
 *
 * The submit is refused while nothing would change (same template, replace):
 * a rebuild with the same format has its own button. The library is loaded
 * only while the dialog is open; the form state lives inside the content,
 * which Radix unmounts on close, so reopening starts from the meeting again.
 */

import { useId, useState } from 'react';
import { RefreshCw } from 'lucide-react';

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
import { useMeetingTemplates } from '@/hooks/useMeetingTemplates';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { isTranscriptTemplate } from '@/lib/meetings/templates';
import type {
  MeetingDetail,
  MeetingReformatRequest,
  MeetingTemplateSummary,
} from '@/types/meetings';

type ReformatMode = MeetingReformatRequest['mode'];
const MODES: readonly ReformatMode[] = ['replace', 'new'];

export interface ReformatDialogProps {
  lng: Language;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  meeting: Pick<MeetingDetail, 'id' | 'template_ref' | 'template_name' | 'has_transcript'>;
  isActing: boolean;
  onSubmit: (request: MeetingReformatRequest) => void;
}

/** Whether the request would change anything: another template, or new minutes. */
function wouldChange(current: string | null, ref: string | null, mode: ReformatMode): boolean {
  if (ref === null) return false;
  return mode === 'new' || ref !== current;
}

function ReformatForm({
  lng,
  meeting,
  templates,
  isActing,
  onSubmit,
}: Omit<ReformatDialogProps, 'open' | 'onOpenChange'> & {
  templates: MeetingTemplateSummary[];
}) {
  const { t } = useTranslation(lng);
  const [ref, setRef] = useState<string | null>(meeting.template_ref);
  const [mode, setMode] = useState<ReformatMode>('replace');
  const selectId = useId();
  const modeName = useId();
  const chosen = templates.find(item => item.ref === ref) ?? null;
  const blocked = !wouldChange(meeting.template_ref, ref, mode);

  const submit = () => {
    if (blocked || isActing || ref === null) return;
    onSubmit({ template_ref: ref, mode });
  };

  return (
    <>
      <div className="space-y-6">
        <TemplateSelect
          lng={lng}
          id={selectId}
          label={t('meetings.detail.reformat.template_label')}
          templates={templates}
          value={ref}
          onChange={setRef}
          placeholder={t('meetings.detail.reformat.choose')}
          triggerClassName="w-full"
        />
        <fieldset className="space-y-3">
          <legend className="text-sm font-medium">
            {t('meetings.detail.reformat.mode_label')}
          </legend>
          {MODES.map(item => (
            <label
              key={item}
              htmlFor={`${modeName}-${item}`}
              className="flex cursor-pointer items-center gap-3 text-sm"
            >
              <input
                id={`${modeName}-${item}`}
                type="radio"
                name={modeName}
                value={item}
                checked={mode === item}
                onChange={() => setMode(item)}
                aria-labelledby={`${modeName}-${item}-label`}
                className="h-4 w-4 accent-primary"
              />
              <span id={`${modeName}-${item}-label`}>
                {t(`meetings.detail.reformat.mode_${item}`)}
              </span>
            </label>
          ))}
        </fieldset>
        <p className="text-xs text-muted-foreground">{t('meetings.detail.reformat.cost_note')}</p>
        {chosen && isTranscriptTemplate(chosen) && (
          <p className="text-sm text-warning">{t('meetings.detail.reformat.transcript_note')}</p>
        )}
      </div>
      <DialogFooter className="mt-6">
        <Button type="button" aria-disabled={blocked || isActing} onClick={submit}>
          <RefreshCw className="mr-1 h-4 w-4" aria-hidden="true" />
          {t('meetings.detail.reformat.submit')}
        </Button>
      </DialogFooter>
    </>
  );
}

export function ReformatDialog(props: ReformatDialogProps) {
  const { lng, open, onOpenChange } = props;
  const { t } = useTranslation(lng);
  const { templates, isLoading } = useMeetingTemplates(open);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent aria-busy={isLoading || undefined}>
        <DialogHeader>
          <DialogTitle>{t('meetings.detail.reformat.title')}</DialogTitle>
          <DialogDescription>{t('meetings.detail.reformat.description')}</DialogDescription>
        </DialogHeader>
        <ReformatForm {...props} templates={templates} />
      </DialogContent>
    </Dialog>
  );
}
