'use client';

/**
 * The minutes template library (ADR-259, recomposed after the owner's review).
 *
 * Two sections, « My templates » first: the rows the user owns (edit,
 * duplicate, delete — alone or as a selection) and the built-ins (preview,
 * add to my templates — alone or as a selection). Each section groups its
 * rows by category, every category folded by default and absent when empty,
 * so thirty entries read as a table of contents rather than a wall. A row
 * exposes its actions ONE way (ADR-208, `RowActions`); the selection bar is
 * the shared one (`ui/selection-bar`). Adding never opens a form: the user
 * shops among the built-ins, then edits from « My templates ».
 */

import { useState } from 'react';
import { Copy, Eye, FolderPlus, LibraryBig, Pencil, Sparkles, Trash2 } from 'lucide-react';

import { TemplateCategoryGlyph } from '@/components/meetings/templateCategoryIcons';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { EmptyState } from '@/components/ui/empty-state';
import { RowActions, type RowAction } from '@/components/ui/row-actions';
import { SelectionBar } from '@/components/ui/selection-bar';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { groupByCategory, isTranscriptTemplate, userTemplateCount } from '@/lib/meetings/templates';
import { pageSelectionState, toggleId } from '@/lib/selection';
import type { MeetingTemplateSummary } from '@/types/meetings';

export interface MeetingTemplateLibraryProps {
  lng: Language;
  templates: MeetingTemplateSummary[];
  maxUserTemplates: number;
  /** A batch is in flight: adding is refused until it answers, the bars' actions are stated busy. */
  busy: boolean;
  /** The template whose full definition is being fetched (preview, edit), if any. */
  busyRef?: string | null;
  onPreview: (ref: string) => void;
  onEdit: (ref: string) => void;
  /** Add built-ins to my templates (one, or the selection). */
  onAddToMine: (refs: string[]) => void;
  /** Duplicate one of my templates to decline it. */
  onDuplicate: (ref: string) => void;
  /** Delete my templates (one, or the selection). */
  onDelete: (refs: string[]) => void;
  /** « Browse the built-ins » from the empty « My templates ». */
  onBrowse: () => void;
  /** The built-ins section, for the page to scroll it into view. */
  builtinsRef?: React.Ref<HTMLElement>;
}

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** The rows of one section in display order: category by category. */
function orderedRefs(items: readonly MeetingTemplateSummary[]): string[] {
  return [...groupByCategory(items).values()].flat().map(item => item.ref);
}

// ---------------------------------------------------------------------------
// Row
// ---------------------------------------------------------------------------

interface TemplateRowProps {
  lng: Language;
  template: MeetingTemplateSummary;
  selected: boolean;
  onToggle: () => void;
  actions: RowAction[];
}

function TemplateRow({ lng, template, selected, onToggle, actions }: TemplateRowProps) {
  const { t } = useTranslation(lng);
  return (
    <li
      aria-label={template.name}
      className="flex items-center gap-2 px-2 py-2.5 transition-colors hover:bg-accent/40 sm:gap-3 sm:px-3"
    >
      {/* 44 px touch target around the native 16 px box; the visually hidden
          text is the checkbox's name. */}
      <label className="flex h-11 w-11 shrink-0 cursor-pointer items-center justify-center">
        <Checkbox checked={selected} onChange={onToggle} />
        <span className="sr-only">
          {t('meetings.templates.select_row', { name: template.name })}
        </span>
      </label>
      <TemplateCategoryGlyph
        category={template.category}
        className="h-4 w-4 shrink-0 text-primary"
      />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="font-semibold text-primary">{template.name}</span>
          <Badge variant="default" size="sm">
            {t('meetings.templates.sections_count', { count: template.sections_count })}
          </Badge>
          {isTranscriptTemplate(template) && (
            <Badge variant="warning" size="sm">
              {t('meetings.templates.transcript_badge')}
            </Badge>
          )}
        </div>
        {template.description && (
          <p className="truncate text-sm text-muted-foreground">{template.description}</p>
        )}
      </div>
      <RowActions
        actions={actions}
        menuLabel={t('meetings.templates.row_actions', { name: template.name })}
      />
    </li>
  );
}

// ---------------------------------------------------------------------------
// Section (my templates | built-ins)
// ---------------------------------------------------------------------------

interface TemplateSectionProps {
  lng: Language;
  title: string;
  icon: typeof LibraryBig;
  items: MeetingTemplateSummary[];
  /** Under the title: the count against the cap, or nothing. */
  caption?: string;
  /** What the section shows when it has no row. */
  empty?: React.ReactNode;
  /** Below the title, when something must be said (the cap). */
  notice?: string;
  rowActions: (template: MeetingTemplateSummary) => RowAction[];
  /** The bar's actions for the selected refs. */
  barActions: (refs: string[], clear: () => void) => React.ReactNode;
  sectionRef?: React.Ref<HTMLElement>;
}

function TemplateSection({
  lng,
  title,
  icon: Icon,
  items,
  caption,
  empty,
  notice,
  rowActions,
  barActions,
  sectionRef,
}: TemplateSectionProps) {
  const { t } = useTranslation(lng);
  const [selected, setSelected] = useState<ReadonlySet<string>>(() => new Set());
  const groups = groupByCategory(items);
  const refs = orderedRefs(items);
  const chosen = refs.filter(ref => selected.has(ref));
  const clear = () => setSelected(new Set());

  return (
    <section ref={sectionRef} aria-label={title} className="space-y-3 scroll-mt-20">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <Icon className="h-5 w-5 text-primary" aria-hidden="true" />
          {title}
        </h2>
        {caption && <p className="text-sm text-muted-foreground">{caption}</p>}
      </div>
      {notice && (
        <p role="status" className="text-sm text-muted-foreground">
          {notice}
        </p>
      )}
      {items.length === 0 ? (
        empty
      ) : (
        <>
          {chosen.length > 0 && (
            <SelectionBar
              regionLabel={t('meetings.templates.selection_region')}
              countLabel={t('meetings.templates.selected_count', { count: chosen.length })}
              selectAllLabel={t('meetings.templates.select_all')}
              clearLabel={t('meetings.templates.clear_selection')}
              pageState={pageSelectionState(refs, selected)}
              onSelectAll={() => setSelected(new Set(refs))}
              onClear={clear}
            >
              {barActions(chosen, clear)}
            </SelectionBar>
          )}
          <Accordion type="multiple" className="rounded-lg border px-3">
            {[...groups.entries()].map(([category, members]) => {
              return (
                <AccordionItem key={category} value={category} className="last:border-b-0">
                  <AccordionTrigger className="gap-3 hover:no-underline">
                    <span className="flex min-w-0 items-center gap-2 text-left">
                      <TemplateCategoryGlyph
                        category={category}
                        className="h-4 w-4 shrink-0 text-primary"
                      />
                      <span className="truncate">
                        {t(`meetings.templates.category.${category}`)}
                      </span>
                      <Badge variant="default" size="sm">
                        {members.length}
                      </Badge>
                    </span>
                  </AccordionTrigger>
                  <AccordionContent className="pb-2">
                    <ul className="divide-y divide-border/60 rounded-md border border-border/60 bg-card/60">
                      {members.map(template => (
                        <TemplateRow
                          key={template.ref}
                          lng={lng}
                          template={template}
                          selected={selected.has(template.ref)}
                          onToggle={() => setSelected(toggleId(selected, template.ref))}
                          actions={rowActions(template)}
                        />
                      ))}
                    </ul>
                  </AccordionContent>
                </AccordionItem>
              );
            })}
          </Accordion>
        </>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Library
// ---------------------------------------------------------------------------

function mineRowActions(
  t: Translate,
  template: MeetingTemplateSummary,
  props: Pick<MeetingTemplateLibraryProps, 'onPreview' | 'onEdit' | 'onDuplicate' | 'onDelete'>,
  loading: boolean
): RowAction[] {
  return [
    {
      key: 'preview',
      label: t('meetings.templates.preview'),
      icon: Eye,
      onSelect: () => props.onPreview(template.ref),
      loading,
    },
    {
      key: 'edit',
      label: t('meetings.templates.edit'),
      icon: Pencil,
      onSelect: () => props.onEdit(template.ref),
      loading,
    },
    {
      key: 'duplicate',
      label: t('meetings.templates.duplicate'),
      icon: Copy,
      onSelect: () => props.onDuplicate(template.ref),
    },
    {
      key: 'delete',
      label: t('meetings.templates.delete'),
      icon: Trash2,
      tone: 'destructive',
      onSelect: () => props.onDelete([template.ref]),
    },
  ];
}

export function MeetingTemplateLibrary(props: MeetingTemplateLibraryProps) {
  const { lng, templates, maxUserTemplates, busy, busyRef, onPreview, onAddToMine, onBrowse } =
    props;
  const { t } = useTranslation(lng);
  const [capNotice, setCapNotice] = useState(false);
  const mine = templates.filter(item => !item.builtin);
  const builtins = templates.filter(item => item.builtin);
  const own = userTemplateCount(templates);
  const atCap = maxUserTemplates > 0 && own >= maxUserTemplates;

  // Adding is refused at the cap: stated on the control and explained once
  // the user tries — never a control that vanished.
  const add = (refs: string[]) => {
    if (busy) return;
    if (atCap) {
      setCapNotice(true);
      return;
    }
    setCapNotice(false);
    onAddToMine(refs);
  };

  return (
    <div className="space-y-8">
      <TemplateSection
        lng={lng}
        title={t('meetings.templates.mine_title')}
        icon={Sparkles}
        items={mine}
        caption={t('meetings.templates.mine_count', { count: own, max: maxUserTemplates })}
        empty={
          <EmptyState
            icon={Sparkles}
            description={t('meetings.templates.empty_custom')}
            action={{
              label: t('meetings.templates.browse_builtins'),
              onClick: onBrowse,
              icon: LibraryBig,
            }}
          />
        }
        rowActions={template => mineRowActions(t, template, props, busyRef === template.ref)}
        barActions={(refs, clear) => (
          <Button
            type="button"
            size="sm"
            variant="destructive"
            aria-disabled={busy}
            onClick={() => {
              if (busy) return;
              props.onDelete(refs);
              clear();
            }}
          >
            <Trash2 className="mr-1 h-4 w-4" aria-hidden="true" />
            {t('meetings.templates.delete_selected', { count: refs.length })}
          </Button>
        )}
      />

      <TemplateSection
        lng={lng}
        sectionRef={props.builtinsRef}
        title={t('meetings.templates.builtin_title')}
        icon={LibraryBig}
        items={builtins}
        notice={
          capNotice ? t('meetings.templates.limit_reached', { count: maxUserTemplates }) : undefined
        }
        rowActions={template => [
          {
            key: 'preview',
            label: t('meetings.templates.preview'),
            icon: Eye,
            onSelect: () => onPreview(template.ref),
            loading: busyRef === template.ref,
          },
          {
            key: 'add',
            label: t('meetings.templates.add_to_mine'),
            icon: FolderPlus,
            onSelect: () => add([template.ref]),
            blocked: atCap,
          },
        ]}
        barActions={(refs, clear) => (
          <Button
            type="button"
            size="sm"
            variant="default"
            aria-disabled={busy || atCap}
            onClick={() => {
              if (busy) return;
              add(refs);
              if (!atCap) clear();
            }}
          >
            <FolderPlus className="mr-1 h-4 w-4" aria-hidden="true" />
            {t('meetings.templates.add_selected', { count: refs.length })}
          </Button>
        )}
      />
    </div>
  );
}
