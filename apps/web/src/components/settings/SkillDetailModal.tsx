'use client';

/**
 * SkillDetailModal — gallery detail sheet (UXR Lot 10, B12).
 *
 * Opens from a gallery card. Shows the bundled preview image (only
 * `assets/preview.png` is ever served — broken/missing falls back to an
 * icon), the localized description, declared output channels (`outputs`
 * frontmatter; null ⇒ the "text" default, labeled as undeclared), and the
 * provenance warning for every NON-admin skill (imported code runs with the
 * user's connectors — the user must trust the source). Actions (download,
 * per-user toggle, delete for user skills) live here.
 */

import { useState } from 'react';
import { AlertTriangle, Blocks, Download, Trash2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { skillPreviewUrl, type Skill } from '@/hooks/useSkills';

/** Translator shape shared with SkillsSettings (react-i18next `t`). */
export type SkillsTranslator = (key: string, options?: Record<string, string>) => string;

/** Channels shown in the modal: declared list, or the undeclared default. */
export function displayedChannels(skill: Pick<Skill, 'outputs'>): {
  channels: string[];
  declared: boolean;
} {
  return skill.outputs?.length
    ? { channels: skill.outputs, declared: true }
    : { channels: ['text'], declared: false };
}

export function SkillDetailModal({
  skill,
  lng,
  t,
  onOpenChange,
  onToggle,
  onDownload,
  onDelete,
  downloading,
  toggling,
}: {
  skill: Skill | null;
  lng: string;
  t: SkillsTranslator;
  onOpenChange: (open: boolean) => void;
  onToggle: (skill: Skill) => void;
  onDownload: (skill: Skill) => void;
  onDelete: (skill: Skill) => void;
  downloading: boolean;
  toggling: boolean;
}) {
  // Per-skill image failure — a name mismatch means a NEW skill was opened,
  // so the image retries naturally (no state-sync effect needed).
  const [previewFailedFor, setPreviewFailedFor] = useState<string | null>(null);

  if (!skill) return null;
  const isAdmin = skill.scope === 'admin';
  const previewFailed = previewFailedFor === skill.name;
  const { channels, declared } = displayedChannels(skill);
  const description =
    skill.descriptions?.[lng] ??
    (isAdmin
      ? t(`settings.skills.desc_${skill.name}`, { defaultValue: skill.description })
      : skill.description);

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 flex-wrap">
            <span className="truncate">{skill.name}</span>
            {skill.category && (
              <Badge variant="secondary" className="text-xs">
                {skill.category}
              </Badge>
            )}
          </DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        {/* Preview — only assets/preview.png is served; fallback icon. */}
        {previewFailed ? (
          <div
            className="flex h-32 items-center justify-center rounded-md border border-border/40 bg-muted/20"
            data-testid="skill-preview-fallback"
          >
            <Blocks className="h-10 w-10 text-muted-foreground/40" aria-hidden />
          </div>
        ) : (
          // eslint-disable-next-line @next/next/no-img-element -- API-served image, next/image cannot proxy credentials
          <img
            src={skillPreviewUrl(skill.name)}
            alt={t('settings.skills.gallery.preview_alt', { name: skill.name })}
            className="max-h-48 w-full rounded-md border border-border/40 object-contain bg-muted/10"
            crossOrigin="use-credentials"
            onError={() => setPreviewFailedFor(skill.name)}
          />
        )}

        {/* Declared output channels */}
        <div className="flex items-center gap-2 flex-wrap text-sm">
          <span className="text-muted-foreground">{t('settings.skills.gallery.channels')}</span>
          {channels.map(channel => (
            <Badge key={channel} variant="outline" className="text-xs">
              {t(`settings.skills.gallery.channel_${channel}`, { defaultValue: channel })}
            </Badge>
          ))}
          {!declared && (
            <span className="text-xs text-muted-foreground italic">
              {t('settings.skills.gallery.channels_undeclared')}
            </span>
          )}
        </div>

        {/* Provenance warning — every non-admin skill. */}
        {!isAdmin && (
          <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-300">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" aria-hidden />
            <p>{t('settings.skills.gallery.provenance_warning')}</p>
          </div>
        )}

        <div className="flex items-center justify-between gap-2 pt-2 border-t border-border/40">
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => onDownload(skill)}
              disabled={downloading}
              aria-label={t('settings.skills.download_button')}
            >
              {downloading ? (
                <LoadingSpinner className="h-4 w-4" />
              ) : (
                <Download className="h-4 w-4" />
              )}
            </Button>
            {!isAdmin && (
              <Button
                variant="ghost"
                size="icon"
                onClick={() => onDelete(skill)}
                aria-label={t('settings.skills.delete_button')}
              >
                <Trash2 className="h-4 w-4 text-destructive" />
              </Button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">
              {t('settings.skills.gallery.enabled_label')}
            </span>
            <Switch
              checked={skill.enabled_for_user}
              onCheckedChange={() => onToggle(skill)}
              disabled={toggling}
              aria-label={t('settings.skills.toggle_skill', { name: skill.name })}
            />
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
