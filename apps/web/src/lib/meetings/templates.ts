/**
 * Library helpers (ADR-259) — pure functions the library page and the
 * settings section compose.
 */

import {
  TEMPLATE_CATEGORIES,
  type MeetingTemplateSummary,
  type TemplateCategory,
  type TemplateSection,
} from '@/types/meetings';

/**
 * Group templates by category in library order (`TEMPLATE_CATEGORIES`),
 * omitting empty categories and keeping the items' own order inside each.
 */
export function groupByCategory(
  items: readonly MeetingTemplateSummary[]
): Map<TemplateCategory, MeetingTemplateSummary[]> {
  const groups = new Map<TemplateCategory, MeetingTemplateSummary[]>();
  for (const category of TEMPLATE_CATEGORIES) {
    const members = items.filter(item => item.category === category);
    if (members.length > 0) groups.set(category, members);
  }
  return groups;
}

/** A transcript template rewrites the whole exchange: long, and paid like a full rewrite. */
export function isTranscriptTemplate(item: Pick<MeetingTemplateSummary, 'category'>): boolean {
  return item.category === 'transcript';
}

/** How many templates the user owns (the cap counts these, never the built-ins). */
export function userTemplateCount(items: readonly MeetingTemplateSummary[]): number {
  return items.filter(item => !item.builtin).length;
}

/**
 * Whether two section lists describe the same structure, field by field and
 * in order. A duplicate whose sections are untouched is created by reference
 * (`duplicate_of`), so the server copies the built-in it knows; one whose
 * sections changed is created from those sections.
 */
export function sectionsEqual(
  left: readonly TemplateSection[],
  right: readonly TemplateSection[]
): boolean {
  if (left.length !== right.length) return false;
  return left.every((section, index) => {
    const other = right[index];
    return (
      section.key === other.key &&
      section.label === other.label &&
      section.instruction === other.instruction &&
      section.kind === other.kind
    );
  });
}
