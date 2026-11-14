'use client';

/**
 * SkillRestoreDialog — confirm going back to a skill's previous version (lot 14).
 *
 * Restoring replaces what the skill says now, so it is asked first. The
 * description says what is NOT lost: the current version becomes the previous
 * one, restorable in turn. The click confirms and closes the dialog; a dialog
 * opened while a restoration still runs keeps its confirm control focusable
 * and refuses a second request (`aria-disabled` plus a guard, never `disabled`).
 */

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import type { SkillsTranslator } from '@/components/settings/SkillDetailModal';
import type { Skill } from '@/hooks/useSkills';
import type { Language } from '@/i18n/settings';
import { skillLifeDay } from '@/lib/skill-life';

export function SkillRestoreDialog({
  skill,
  lng,
  t,
  busy,
  onCancel,
  onConfirm,
}: {
  /** The skill to restore; null keeps the dialog closed. */
  skill: Skill | null;
  lng: Language;
  t: SkillsTranslator;
  busy: boolean;
  onCancel: () => void;
  onConfirm: (skill: Skill) => void;
}) {
  const replaced = skill?.previous_version_at;
  return (
    <AlertDialog open={skill !== null} onOpenChange={open => !open && onCancel()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('settings.skills.previous.confirm_title')}</AlertDialogTitle>
          <AlertDialogDescription>
            {t('settings.skills.previous.confirm_description', {
              name: skill?.name ?? '',
              date: replaced ? skillLifeDay(replaced, lng) : '',
            })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
          <AlertDialogAction
            aria-disabled={busy || undefined}
            onClick={event => {
              if (busy) {
                event.preventDefault();
                return;
              }
              if (skill) onConfirm(skill);
            }}
          >
            {t('settings.skills.previous.confirm_action')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
