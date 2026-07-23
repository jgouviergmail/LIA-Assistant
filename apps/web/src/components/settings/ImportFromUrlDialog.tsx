'use client';

/**
 * ImportFromUrlDialog — install a skill from an https URL (UXR Lot 10, B12).
 *
 * The backend is the authority (SSRF validation, redirect refusal, size cap,
 * then the SAME hardened pipeline as file upload); this dialog only guides:
 * https-only input, provenance warning BEFORE importing, and stable-coded
 * error toasts (`url_*` detail prefixes are a backend contract).
 */

import { useState } from 'react';
import { AlertTriangle, Link2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import type { Skill } from '@/hooks/useSkills';
import type { SkillsTranslator } from '@/components/settings/SkillDetailModal';

/** Map a backend error message to its i18n toast key (stable prefixes). */
export function urlImportErrorKey(message: string): string {
  if (message.startsWith('url_not_https')) return 'settings.skills.url_import.error_not_https';
  if (message.startsWith('url_blocked')) return 'settings.skills.url_import.error_blocked';
  if (message.startsWith('url_too_large')) return 'settings.skills.url_import.error_too_large';
  if (message.startsWith('url_not_skill_content')) {
    return 'settings.skills.url_import.error_not_skill';
  }
  if (message.startsWith('url_fetch_failed')) return 'settings.skills.url_import.error_fetch';
  return 'settings.skills.import_error';
}

export function ImportFromUrlDialog({
  open,
  t,
  onOpenChange,
  onImport,
  importing,
}: {
  open: boolean;
  t: SkillsTranslator;
  onOpenChange: (open: boolean) => void;
  onImport: (url: string) => Promise<Skill | undefined>;
  importing: boolean;
}) {
  const [url, setUrl] = useState('');
  const canSubmit = url.trim().toLowerCase().startsWith('https://') && !importing;

  const handleImport = async () => {
    try {
      const skill = await onImport(url.trim());
      if (skill) {
        toast.success(t('settings.skills.import_success', { name: skill.name }));
        setUrl('');
        onOpenChange(false);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : '';
      toast.error(t(urlImportErrorKey(message)));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Link2 className="h-4 w-4" aria-hidden />
            {t('settings.skills.url_import.title')}
          </DialogTitle>
          <DialogDescription>{t('settings.skills.url_import.description')}</DialogDescription>
        </DialogHeader>

        <Input
          type="url"
          value={url}
          onChange={e => setUrl(e.target.value)}
          placeholder="https://example.com/my-skill.zip"
          aria-label={t('settings.skills.url_import.input_label')}
          onKeyDown={e => {
            if (e.key === 'Enter' && canSubmit) {
              e.preventDefault();
              void handleImport();
            }
          }}
        />

        <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-300">
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" aria-hidden />
          <p>{t('settings.skills.gallery.provenance_warning')}</p>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={importing}>
            {t('common.cancel')}
          </Button>
          <Button onClick={() => void handleImport()} disabled={!canSubmit}>
            {importing ? (
              <LoadingSpinner className="mr-2 h-4 w-4" />
            ) : (
              <Link2 className="h-4 w-4 mr-1" />
            )}
            {t('settings.skills.url_import.confirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
