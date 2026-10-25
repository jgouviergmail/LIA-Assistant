/**
 * The « + » offers what LIA generated for the person (owner request 2026-10-24).
 *
 * An image joins the message as an image, a document with its text — a COPY
 * the API makes of a live file of the gallery (ADR-279): kept, or before its
 * deadline. One family at a time, as the gallery lists them, each a page and
 * its exact total.
 */

'use client';

import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FileText, Image as ImageIcon, Images } from 'lucide-react';

import { AttachSourcePickerDialog, type PickerWords } from './AttachSourcePickerDialog';
import type { AddServerAttachmentOutcome, ServerAttachmentMeta } from '@/hooks/useFileUpload';
import { useNeedlePage } from '@/hooks/useNeedlePage';
import { copyAttachSource } from '@/lib/attach-sources';
import { formatFileSize } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { GeneratedAsset, GeneratedAssetFamily } from '@/types/generated-assets';

const WORDS: PickerWords = {
  title: 'chat.generated_picker.title',
  description: 'chat.generated_picker.description',
  searchPlaceholder: 'chat.attach_picker.search_placeholder',
  loading: 'chat.generated_picker.loading',
  empty: 'chat.generated_picker.empty',
  emptySearch: 'chat.generated_picker.empty_search',
  error: 'chat.generated_picker.error',
  moreHint: 'chat.attach_picker.more_hint',
  remaining: 'chat.attach_picker.remaining',
  attach: 'chat.attach_picker.attach',
  alreadyAttached: 'chat.attach_picker.already_attached',
  attachError: 'chat.attach_picker.attach_error',
};

/** The families the picker offers: what the person asked LIA to make. */
const FAMILIES: ReadonlyArray<GeneratedAssetFamily> = ['images', 'documents'];

interface GeneratedFilePickerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  remaining: number;
  onAttached: (meta: ServerAttachmentMeta) => AddServerAttachmentOutcome;
}

function FamilyTabs({
  family,
  onFamily,
}: {
  family: GeneratedAssetFamily;
  onFamily: (family: GeneratedAssetFamily) => void;
}) {
  const { t } = useTranslation();
  const group = useId();
  // Native radios: the arrows move between families and Tab enters the group,
  // as the platform does — a styled label is all the segmented look needs.
  return (
    <fieldset className="flex gap-1">
      <legend className="sr-only">{t('chat.generated_picker.family')}</legend>
      {FAMILIES.map(value => (
        <label
          key={value}
          className={cn(
            'cursor-pointer rounded-md border px-3 py-1.5 text-sm transition-colors has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring',
            family === value ? 'border-primary bg-primary/10 text-primary' : 'hover:bg-accent/50'
          )}
        >
          <input
            type="radio"
            name={group}
            value={value}
            checked={family === value}
            onChange={() => onFamily(value)}
            aria-labelledby={`${group}-${value}`}
            className="sr-only"
          />
          <span id={`${group}-${value}`}>{t(`chat.generated_picker.family_${value}`)}</span>
        </label>
      ))}
    </fieldset>
  );
}

export function GeneratedFilePickerDialog(props: GeneratedFilePickerDialogProps) {
  const [needle, setNeedle] = useState('');
  const [family, setFamily] = useState<GeneratedAssetFamily>('images');
  const page = useNeedlePage<GeneratedAsset>('/generated-assets', needle, props.open, {
    family,
  });
  return (
    <AttachSourcePickerDialog<GeneratedAsset>
      {...props}
      icon={Images}
      itemIcon={family === 'images' ? ImageIcon : FileText}
      words={WORDS}
      needle={needle}
      onNeedleChange={setNeedle}
      page={page}
      toolbar={<FamilyTabs family={family} onFamily={setFamily} />}
      idOf={asset => asset.id}
      labelOf={asset => asset.title || asset.original_filename}
      metaOf={asset => <span>{formatFileSize(asset.file_size)}</span>}
      copy={asset => copyAttachSource({ kind: 'generated', id: asset.id })}
    />
  );
}
