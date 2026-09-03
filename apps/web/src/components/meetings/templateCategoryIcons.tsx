/**
 * One glyph per template category (ADR-259): the same icon in front of a
 * category heading, a template title and a picker group, in the theme colour
 * (a title icon is never grey — owner rule 2026-08-05).
 */

import {
  AudioLines,
  Brain,
  Briefcase,
  GraduationCap,
  Heart,
  type LucideIcon,
  Sparkles,
  Users,
  Wrench,
} from 'lucide-react';

import type { TemplateCategory } from '@/types/meetings';

export const TEMPLATE_CATEGORY_ICONS: Record<TemplateCategory, LucideIcon> = {
  custom: Sparkles,
  meeting: Users,
  transcript: AudioLines,
  analysis: Brain,
  business: Briefcase,
  technical: Wrench,
  personal: Heart,
  learning: GraduationCap,
};

export function templateCategoryIcon(category: TemplateCategory): LucideIcon {
  return TEMPLATE_CATEGORY_ICONS[category];
}

/**
 * The glyph as a component, so a caller never resolves a component during
 * its own render (`react-hooks/static-components`): the lookup happens here.
 */
export function TemplateCategoryGlyph({
  category,
  className,
}: {
  category: TemplateCategory;
  className?: string;
}) {
  const Icon = TEMPLATE_CATEGORY_ICONS[category];
  return <Icon className={className} aria-hidden="true" />;
}
