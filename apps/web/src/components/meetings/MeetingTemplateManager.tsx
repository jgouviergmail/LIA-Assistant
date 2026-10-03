'use client';

/**
 * MeetingTemplateManager — the minutes template library as a working screen
 * (ADR-259): the library itself, a read-only preview, or the form — which
 * only creates and edits.
 *
 * Mounted by two doors with ONE implementation: the standalone page
 * `/dashboard/meetings/templates` and the « Templates » block of the
 * meetings settings section (owner, 2026-10-03: the meetings settings are one
 * page). The caller owns the `library` read so a settings section that also
 * offers the default-format select shares the same list — a template created
 * here appears there without a second request.
 *
 * Adding a built-in (or duplicating one of mine) is one request that answers
 * with the new rows; deleting asks first and, when the default-format
 * preference pointed at a deleted row, says that it went back to automatic.
 * Every batch reports what it skipped and why.
 */

import { useRef, useState } from 'react';
import { Plus } from 'lucide-react';
import { toast } from 'sonner';

import { MeetingTemplateForm } from '@/components/meetings/MeetingTemplateForm';
import { MeetingTemplateLibrary } from '@/components/meetings/MeetingTemplateLibrary';
import { MeetingTemplatePreview } from '@/components/meetings/MeetingTemplatePreview';
import { SectionToolbar } from '@/components/settings/SectionToolbar';
import { LoadingAnnouncement } from '@/components/ui/loading-announcement';
import { Skeleton } from '@/components/ui/skeleton';
import { useConfirm } from '@/components/ui/use-confirm';
import type { UseMeetingTemplatesReturn } from '@/hooks/useMeetingTemplates';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { skippedSentence, type Translate } from '@/lib/batch-report';
import { rederiveSectionKeys, uniqueSectionKey } from '@/lib/meetings/template-keys';
import { userTemplateCount } from '@/lib/meetings/templates';
import type { MeetingTemplate, MeetingTemplateUpdate } from '@/types/meetings';

export interface MeetingTemplateManagerProps {
  lng: Language;
  /** The library read, owned by the caller (one read per screen). */
  library: UseMeetingTemplatesReturn;
  /**
   * Mounted inside another surface (a settings block) rather than as a page:
   * the library's section headings step down to the block's scale.
   */
  nested?: boolean;
}

type View =
  | { kind: 'list' }
  | { kind: 'preview'; template: MeetingTemplate }
  | { kind: 'form'; intent: 'create'; source: null }
  | { kind: 'form'; intent: 'edit'; source: MeetingTemplate };

/** The first draft of a template built from nothing: one section to fill. */
function blankTemplate(label: string): MeetingTemplateUpdate {
  return {
    name: '',
    description: null,
    category: 'custom',
    sections: [{ key: uniqueSectionKey(label, []), label, instruction: '', kind: 'bullets' }],
  };
}

function initialValues(view: Extract<View, { kind: 'form' }>, t: Translate): MeetingTemplateUpdate {
  if (view.intent === 'create') return blankTemplate(t('meetings.settings.new_section_label'));
  const { source } = view;
  return {
    name: source.name,
    description: source.description,
    category: source.category,
    sections: source.sections,
  };
}

function LibrarySkeleton() {
  return (
    <div className="space-y-3">
      <LoadingAnnouncement />
      {[1, 2, 3, 4].map(i => (
        <Skeleton key={i} className="h-14 w-full" />
      ))}
    </div>
  );
}

/** The batches, with their toasts, out of the render function. */
function useLibraryBatches(library: UseMeetingTemplatesReturn, t: Translate) {
  const { confirm, confirmDialog } = useConfirm();

  const addToMine = async (refs: string[]) => {
    const result = await library.bulkDuplicate(refs);
    if (result === null) {
      toast.error(t('meetings.templates.save_failed'));
      return;
    }
    if (result.created.length > 0) {
      toast.success(t('meetings.templates.added', { count: result.created.length }));
    }
    if (result.skipped.length > 0) {
      toast.info(skippedSentence(t, 'meetings.templates', result.skipped));
    }
  };

  const remove = async (refs: string[]) => {
    const name = library.templates.find(item => item.ref === refs[0])?.name ?? '';
    const ok = await confirm({
      title: t('meetings.templates.confirm_delete_title', { count: refs.length }),
      description: t('meetings.templates.confirm_delete_description', { count: refs.length, name }),
      confirmLabel: t('meetings.templates.delete_selected', { count: refs.length }),
    });
    if (!ok) return;
    const result = await library.bulkDelete(refs);
    if (result === null) {
      toast.error(t('meetings.templates.delete_failed'));
      return;
    }
    if (result.deleted.length > 0) {
      toast.success(t('meetings.templates.deleted', { count: result.deleted.length }));
    }
    if (result.skipped.length > 0) {
      toast.info(skippedSentence(t, 'meetings.templates', result.skipped));
    }
    if (result.preference_reset) toast.info(t('meetings.templates.preference_reset'));
  };

  return { addToMine, remove, confirmDialog };
}

export function MeetingTemplateManager({
  lng,
  library,
  nested = false,
}: MeetingTemplateManagerProps) {
  const { t } = useTranslation(lng);
  const { addToMine, remove, confirmDialog } = useLibraryBatches(library, t);
  const [view, setView] = useState<View>({ kind: 'list' });
  const [capNotice, setCapNotice] = useState(false);
  const [busyRef, setBusyRef] = useState<string | null>(null);
  const builtinsRef = useRef<HTMLElement>(null);

  const ownCount = userTemplateCount(library.templates);
  const atCap = library.maxUserTemplates > 0 && ownCount >= library.maxUserTemplates;

  const withTemplate = async (ref: string, next: (template: MeetingTemplate) => View) => {
    setBusyRef(ref);
    try {
      const template = await library.load(ref);
      if (template === null) {
        toast.error(t('meetings.templates.load_failed'));
        return;
      }
      setView(next(template));
    } finally {
      setBusyRef(null);
    }
  };

  const openCreate = () => {
    if (atCap) {
      setCapNotice(true);
      return;
    }
    setCapNotice(false);
    setView({ kind: 'form', intent: 'create', source: null });
  };

  const onSubmit = async (
    formView: Extract<View, { kind: 'form' }>,
    values: MeetingTemplateUpdate
  ) => {
    const saved =
      formView.intent === 'edit'
        ? await library.update(formView.source.ref, values)
        : await library.create({ ...values, sections: rederiveSectionKeys(values.sections) });
    if (saved === null) {
      toast.error(t('meetings.templates.save_failed'));
      return;
    }
    toast.success(t('meetings.templates.saved'));
    setView({ kind: 'list' });
  };

  return (
    <>
      {confirmDialog}

      {view.kind === 'list' && (
        <div className={nested ? 'space-y-4' : 'space-y-6'}>
          <SectionToolbar
            count=""
            menuLabel={t('common.more_actions')}
            primary={{
              key: 'new',
              label: t('meetings.templates.new'),
              icon: Plus,
              onSelect: openCreate,
              blocked: atCap,
            }}
          />
          {capNotice && (
            <p role="status" className="text-sm text-muted-foreground">
              {t('meetings.templates.limit_reached', { count: library.maxUserTemplates })}
            </p>
          )}
          {library.isLoading ? (
            <LibrarySkeleton />
          ) : (
            <MeetingTemplateLibrary
              lng={lng}
              nested={nested}
              templates={library.templates}
              maxUserTemplates={library.maxUserTemplates}
              busy={library.isSaving}
              busyRef={busyRef}
              builtinsRef={builtinsRef}
              onPreview={ref => void withTemplate(ref, template => ({ kind: 'preview', template }))}
              onEdit={ref =>
                void withTemplate(ref, source => ({ kind: 'form', intent: 'edit', source }))
              }
              onAddToMine={refs => void addToMine(refs)}
              onDuplicate={ref => void addToMine([ref])}
              onDelete={refs => void remove(refs)}
              onBrowse={() =>
                builtinsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
              }
            />
          )}
        </div>
      )}

      {view.kind === 'preview' && (
        <MeetingTemplatePreview
          lng={lng}
          template={view.template}
          onBack={() => setView({ kind: 'list' })}
          onAddToMine={
            view.template.builtin ? () => void addToMine([view.template.ref]) : undefined
          }
          addBlocked={atCap}
        />
      )}

      {view.kind === 'form' && (
        <MeetingTemplateForm
          key={`${view.intent}:${view.source?.ref ?? ''}`}
          lng={lng}
          title={t(
            view.intent === 'create'
              ? 'meetings.templates.form.create_title'
              : 'meetings.templates.form.edit_title'
          )}
          initial={initialValues(view, t)}
          isSaving={library.isSaving}
          onSubmit={values => void onSubmit(view, values)}
          onCancel={() => setView({ kind: 'list' })}
        />
      )}
    </>
  );
}
