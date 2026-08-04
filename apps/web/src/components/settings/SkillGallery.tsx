'use client';

/**
 * SkillGallery — card grid for one skill scope (UXR Lot 10, B12).
 *
 * Each card is a real `<button>` opening the detail modal; the per-user
 * toggle stays inline as a SIBLING control (never nested inside the button —
 * a11y invariant). Badges surface category and capability hints at a glance.
 */

import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import type { Skill } from '@/hooks/useSkills';
import type { SkillsTranslator } from '@/components/settings/SkillDetailModal';
import { skillTraitTone } from '@/lib/status-tone';

function CardBadges({ skill, t }: { skill: Skill; t: SkillsTranslator }) {
  return (
    <>
      {/* Toned by TYPE through `skillTraitTone` (ADR-207): identity in the
          theme's primary, the permanent context cost in amber, plain
          capabilities neutral. These same labels had already drifted between
          this gallery and the admin section. */}
      {skill.category && (
        <Badge variant={skillTraitTone('category')} className="text-xs">
          {skill.category}
        </Badge>
      )}
      {skill.always_loaded && (
        <Badge variant={skillTraitTone('always_loaded')} className="shrink-0 text-xs">
          {t('settings.skills.always_loaded')}
        </Badge>
      )}
      {skill.has_scripts && (
        <Badge variant={skillTraitTone('has_scripts')} className="shrink-0 text-xs">
          {t('settings.skills.has_scripts')}
        </Badge>
      )}
      {skill.dialogue && (
        <Badge variant={skillTraitTone('dialogue')} className="shrink-0 text-xs">
          {t('settings.skills.gallery.dialogue_badge')}
        </Badge>
      )}
    </>
  );
}

export function SkillGallery({
  skills,
  lng,
  t,
  onOpen,
  onToggle,
  toggling,
}: {
  skills: Skill[];
  lng: string;
  t: SkillsTranslator;
  onOpen: (skill: Skill) => void;
  onToggle: (skill: Skill) => void;
  toggling: boolean;
}) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {skills.map(skill => {
        const isAdmin = skill.scope === 'admin';
        const description =
          skill.descriptions?.[lng] ??
          (isAdmin
            ? t(`settings.skills.desc_${skill.name}`, { defaultValue: skill.description })
            : skill.description);
        return (
          <div
            key={skill.name}
            className={`flex items-start gap-2 rounded-lg border p-3 ${
              isAdmin ? 'bg-card/50' : 'bg-card'
            }`}
          >
            <button
              type="button"
              onClick={() => onOpen(skill)}
              aria-label={t('settings.skills.gallery.open_details', { name: skill.name })}
              className="min-w-0 flex-1 text-left rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span className="flex items-center gap-2 flex-wrap">
                <span className="font-medium text-sm truncate">{skill.name}</span>
                <CardBadges skill={skill} t={t} />
              </span>
              <span className="mt-1 block text-xs text-muted-foreground line-clamp-2">
                {description}
              </span>
            </button>
            <Switch
              checked={skill.enabled_for_user}
              onCheckedChange={() => onToggle(skill)}
              disabled={toggling}
              aria-label={t('settings.skills.toggle_skill', { name: skill.name })}
            />
          </div>
        );
      })}
    </div>
  );
}
