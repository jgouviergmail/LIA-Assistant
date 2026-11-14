'use client';

import { Copy } from '@/lib/icons';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';

interface CopyValueFieldProps {
  /** The value's id, unique on the page; its label's id is derived from it. */
  id: string;
  /** The visible label, already translated. */
  label: string;
  /** What the person copies into another system. */
  value: string;
  /** The copy button's accessible name, already translated. */
  copyLabel: string;
  /** What the toast says once the value is copied, already translated. */
  copiedMessage: string;
}

/**
 * A value the person copies into another system, READ WHOLE at any width: a
 * long address or a secret wraps, where a read-only field hid its end behind
 * a scroll on a phone (ADR-386). Named by its label as a group; the copy
 * button is named after what it copies — several on one screen would otherwise
 * all read « copy » to a screen reader. One tap selects it all.
 *
 * Never offered to the selection assist (`data-selection-assist="off"`): a
 * selected secret must not be handed to a model.
 */
export function CopyValueField({
  id,
  label,
  value,
  copyLabel,
  copiedMessage,
}: CopyValueFieldProps) {
  const { t } = useTranslation();
  const labelId = `${id}-label`;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      toast.success(copiedMessage);
    } catch {
      toast.error(t('common.copyFailed'));
    }
  };
  return (
    <div role="group" aria-labelledby={labelId} className="space-y-3" data-selection-assist="off">
      <p id={labelId} className="text-sm font-medium leading-none">
        {label}
      </p>
      <div className="flex items-start gap-2">
        <code
          id={id}
          className="min-w-0 flex-1 select-all break-all rounded-md border bg-muted px-3 py-2 font-mono text-sm leading-relaxed"
        >
          {value}
        </code>
        <Button
          type="button"
          variant="outline"
          size="icon"
          className="shrink-0"
          aria-label={copyLabel}
          onClick={() => void copy()}
        >
          <Copy className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}
