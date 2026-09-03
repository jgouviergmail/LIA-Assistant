'use client';

/**
 * Editing the minutes structure (ADR-258, readable form ADR-259): the ordered
 * sections LIA fills.
 *
 * A section is a heading the reader sees, a format (prose, bullets, topics,
 * action items, transcript) and an instruction the model follows. The
 * instruction is the long part, so it folds behind a named disclosure and the
 * card reads « Section N · heading · format » at a glance; a section whose
 * instruction is empty opens itself — that is required work, not detail.
 * The stable key the API requires is derived from the heading once and kept
 * (`template-keys.ts`), so a renamed heading does not orphan the section in
 * already-generated minutes.
 */

import { useEffect, useRef, useState } from 'react';
import { ArrowDown, ArrowUp, ChevronRight, Plus, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { uniqueSectionKey } from '@/lib/meetings/template-keys';
import { cn } from '@/lib/utils';
import { SECTION_KINDS, type SectionKind, type TemplateSection } from '@/types/meetings';

/** Mirrors the API bound (`MAX_TEMPLATE_SECTIONS`). */
export const MAX_TEMPLATE_SECTIONS = 12;

interface MeetingTemplateEditorProps {
  lng: Language;
  sections: TemplateSection[];
  onChange: (next: TemplateSection[]) => void;
}

function move<T>(items: T[], from: number, to: number): T[] {
  if (to < 0 || to >= items.length) return items;
  const next = [...items];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

/** Keys whose instruction is empty: they must be open, the user has work there. */
function keysNeedingWork(sections: TemplateSection[]): string[] {
  return sections.filter(s => !s.instruction.trim()).map(s => s.key);
}

interface SectionCardProps {
  lng: Language;
  section: TemplateSection;
  index: number;
  count: number;
  open: boolean;
  onToggle: () => void;
  onUpdate: (patch: Partial<TemplateSection>) => void;
  onMove: (to: number) => void;
  onRemove: () => void;
  textareaRef: (element: HTMLTextAreaElement | null) => void;
}

function SectionCard({
  lng,
  section,
  index,
  count,
  open,
  onToggle,
  onUpdate,
  onMove,
  onRemove,
  textareaRef,
}: SectionCardProps) {
  const { t } = useTranslation(lng);
  const base = `template-section-${index}`;
  const panelId = `${base}-instruction-panel`;
  const missing = !section.instruction.trim();
  const preview = section.instruction.split('\n').find(line => line.trim()) ?? '';
  return (
    <li className="space-y-3 rounded-md border border-border/60 p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-muted-foreground">
          {t('meetings.settings.section_position', { position: index + 1 })}
        </span>
        <span className="inline-flex gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={t('meetings.settings.move_up', { label: section.label })}
            aria-disabled={index === 0}
            onClick={() => index > 0 && onMove(index - 1)}
          >
            <ArrowUp className="h-4 w-4" aria-hidden="true" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={t('meetings.settings.move_down', { label: section.label })}
            aria-disabled={index === count - 1}
            onClick={() => index < count - 1 && onMove(index + 1)}
          >
            <ArrowDown className="h-4 w-4" aria-hidden="true" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="text-destructive"
            aria-label={t('meetings.settings.remove_section', { label: section.label })}
            aria-disabled={count <= 1}
            onClick={() => count > 1 && onRemove()}
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
          </Button>
        </span>
      </div>
      <div className="grid gap-3 sm:grid-cols-[1fr_12rem]">
        <div className="space-y-3">
          <Label htmlFor={`${base}-label`}>{t('meetings.settings.section_label')}</Label>
          <Input
            id={`${base}-label`}
            value={section.label}
            maxLength={80}
            onChange={e => onUpdate({ label: e.target.value })}
          />
        </div>
        <div className="space-y-3">
          <Label htmlFor={`${base}-kind`}>{t('meetings.settings.section_kind')}</Label>
          <Select
            value={section.kind}
            onValueChange={value => onUpdate({ kind: value as SectionKind })}
          >
            <SelectTrigger id={`${base}-kind`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SECTION_KINDS.map(kind => (
                <SelectItem key={kind} value={kind}>
                  {t(`meetings.settings.kind_${kind}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      {/* The instruction folds: a disclosure button names it, the collapsed
          row keeps a one-line preview so the structure stays readable. */}
      <div className="flex min-w-0 items-center gap-2 text-xs">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={onToggle}
          className="inline-flex shrink-0 items-center gap-1 rounded-md py-1 font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <ChevronRight
            className={cn(
              'h-4 w-4 shrink-0 text-primary transition-transform',
              open && 'rotate-90'
            )}
            aria-hidden="true"
          />
          {t('meetings.settings.instruction_toggle')}
        </button>
        {/* The preview sits NEXT to the button: inside it, it would join the
            accessible name and change it with every keystroke. */}
        {!open && (
          <span className="min-w-0 truncate text-muted-foreground">
            {preview || t('meetings.settings.instruction_preview_empty')}
          </span>
        )}
      </div>
      {missing && (
        <p className="text-xs text-destructive">{t('meetings.settings.instruction_missing')}</p>
      )}
      <div id={panelId} className={cn(!open && 'hidden')}>
        {open && (
          <div className="space-y-3">
            <Label htmlFor={`${base}-instruction`} className="sr-only">
              {t('meetings.settings.section_instruction')}
            </Label>
            <Textarea
              id={`${base}-instruction`}
              ref={textareaRef}
              rows={3}
              maxLength={600}
              aria-invalid={missing}
              value={section.instruction}
              onChange={e => onUpdate({ instruction: e.target.value })}
            />
          </div>
        )}
      </div>
    </li>
  );
}

export function MeetingTemplateEditor({ lng, sections, onChange }: MeetingTemplateEditorProps) {
  const { t } = useTranslation(lng);
  // Open = the user opened it, or its instruction is empty (required work).
  const [openKeys, setOpenKeys] = useState<ReadonlySet<string>>(
    () => new Set(keysNeedingWork(sections))
  );
  // The key whose instruction must receive focus once its textarea exists —
  // a ref, not state: the effect below consumes it without re-rendering.
  const pendingFocus = useRef<string | null>(null);
  const textareas = useRef(new Map<string, HTMLTextAreaElement>());

  // Focus the instruction of a section that was just added, once it exists.
  useEffect(() => {
    const key = pendingFocus.current;
    if (key === null) return;
    const element = textareas.current.get(key);
    if (element) {
      element.focus();
      pendingFocus.current = null;
    }
  }, [sections]);

  const isOpen = (section: TemplateSection) =>
    openKeys.has(section.key) || !section.instruction.trim();

  const toggle = (section: TemplateSection) => {
    // An empty instruction is required work: it cannot be folded away, and
    // refusing here keeps its key in `openKeys` so the first typed character
    // does not fold the panel under the user's fingers.
    if (!section.instruction.trim()) return;
    const next = new Set(openKeys);
    if (isOpen(section)) {
      next.delete(section.key);
    } else {
      next.add(section.key);
    }
    setOpenKeys(next);
  };

  const update = (index: number, patch: Partial<TemplateSection>) =>
    onChange(sections.map((section, i) => (i === index ? { ...section, ...patch } : section)));

  const add = () => {
    if (sections.length >= MAX_TEMPLATE_SECTIONS) return;
    const label = t('meetings.settings.new_section_label');
    const key = uniqueSectionKey(
      label,
      sections.map(s => s.key)
    );
    setOpenKeys(new Set([...openKeys, key]));
    pendingFocus.current = key;
    onChange([...sections, { key, label, instruction: '', kind: 'bullets' }]);
  };

  return (
    <div className="space-y-4">
      <ol className="space-y-3">
        {sections.map((section, index) => (
          <SectionCard
            key={section.key}
            lng={lng}
            section={section}
            index={index}
            count={sections.length}
            open={isOpen(section)}
            onToggle={() => toggle(section)}
            onUpdate={patch => update(index, patch)}
            onMove={to => onChange(move(sections, index, to))}
            onRemove={() => onChange(sections.filter((_, i) => i !== index))}
            textareaRef={element => {
              if (element) textareas.current.set(section.key, element);
              else textareas.current.delete(section.key);
            }}
          />
        ))}
      </ol>
      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-disabled={sections.length >= MAX_TEMPLATE_SECTIONS}
          onClick={add}
        >
          <Plus className="mr-1 h-4 w-4" aria-hidden="true" />
          {t('meetings.settings.add_section')}
        </Button>
        <span className="text-xs text-muted-foreground">
          {t('meetings.settings.max_sections', { count: MAX_TEMPLATE_SECTIONS })}
        </span>
      </div>
    </div>
  );
}
