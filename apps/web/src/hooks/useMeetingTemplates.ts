'use client';

/**
 * The minutes template library (ADR-259): every built-in plus the user's own.
 *
 * The list is loaded once; every write returns the server's row and updates
 * the list in place (a created template joins it, an updated one replaces its
 * summary, a removed one leaves). A failed write keeps the list and exposes
 * the error — the caller toasts.
 */

import { useCallback, useEffect, useState } from 'react';

import { useStaleGuard } from '@/hooks/useStaleGuard';
import { logger } from '@/lib/logger';
import { meetingsApi } from '@/lib/meetings/api';
import type {
  MeetingTemplate,
  MeetingTemplateBulkDeleteResponse,
  MeetingTemplateBulkDuplicateResponse,
  MeetingTemplateCreate,
  MeetingTemplateSummary,
  MeetingTemplateUpdate,
} from '@/types/meetings';

export interface UseMeetingTemplatesReturn {
  templates: MeetingTemplateSummary[];
  /** How many templates the user may keep (built-ins not counted). */
  maxUserTemplates: number;
  isLoading: boolean;
  isSaving: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
  /** One template with its sections (built-in or owned). */
  load: (ref: string) => Promise<MeetingTemplate | null>;
  create: (request: MeetingTemplateCreate) => Promise<MeetingTemplate | null>;
  update: (ref: string, request: MeetingTemplateUpdate) => Promise<MeetingTemplate | null>;
  remove: (ref: string) => Promise<boolean>;
  /** Add several templates to my templates; the created rows join the list. */
  bulkDuplicate: (refs: string[]) => Promise<MeetingTemplateBulkDuplicateResponse | null>;
  /** Delete several of my templates; the deleted rows leave the list. */
  bulkDelete: (refs: string[]) => Promise<MeetingTemplateBulkDeleteResponse | null>;
}

/** The list entry a full template answers with. */
function summaryOf(template: MeetingTemplate): MeetingTemplateSummary {
  return {
    ref: template.ref,
    name: template.name,
    description: template.description,
    category: template.category,
    builtin: template.builtin,
    sections_count: template.sections.length,
    auto_selectable: template.auto_selectable,
  };
}

export function useMeetingTemplates(enabled = true): UseMeetingTemplatesReturn {
  const [templates, setTemplates] = useState<MeetingTemplateSummary[]>([]);
  const [maxUserTemplates, setMaxUserTemplates] = useState(0);
  const [isLoading, setIsLoading] = useState(enabled);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const guard = useStaleGuard();

  const refetch = useCallback(async () => {
    if (!enabled) return;
    const isStale = guard.begin();
    try {
      const library = await meetingsApi.templates();
      if (isStale()) return;
      setTemplates(library.items);
      setMaxUserTemplates(library.max_user_templates);
      setError(null);
    } catch (err) {
      if (isStale()) return;
      setError(err instanceof Error ? err : new Error(String(err)));
      logger.error('meeting_templates_load_failed', err as Error, {
        component: 'useMeetingTemplates',
      });
    } finally {
      if (!isStale()) setIsLoading(false);
    }
  }, [enabled, guard]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  const write = useCallback(
    async <T>(operation: () => Promise<T>, apply: (result: T) => void): Promise<T | null> => {
      setIsSaving(true);
      try {
        const result = await operation();
        apply(result);
        setError(null);
        return result;
      } catch (err) {
        setError(err instanceof Error ? err : new Error(String(err)));
        return null;
      } finally {
        setIsSaving(false);
      }
    },
    []
  );

  const load = useCallback(async (ref: string) => {
    try {
      return await meetingsApi.template(ref);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
      return null;
    }
  }, []);

  const create = useCallback(
    (request: MeetingTemplateCreate) =>
      write(
        () => meetingsApi.createTemplate(request),
        created => setTemplates(current => [...current, summaryOf(created)])
      ),
    [write]
  );

  const update = useCallback(
    (ref: string, request: MeetingTemplateUpdate) =>
      write(
        () => meetingsApi.updateTemplate(ref, request),
        updated =>
          setTemplates(current =>
            current.map(item => (item.ref === ref ? summaryOf(updated) : item))
          )
      ),
    [write]
  );

  const bulkDuplicate = useCallback(
    (refs: string[]) =>
      write(
        () => meetingsApi.bulkDuplicateTemplates({ refs }),
        result => setTemplates(current => [...current, ...result.created])
      ),
    [write]
  );

  const bulkDelete = useCallback(
    (refs: string[]) =>
      write(
        () => meetingsApi.bulkDeleteTemplates({ refs }),
        result => {
          const gone = new Set(result.deleted);
          setTemplates(current => current.filter(item => !gone.has(item.ref)));
        }
      ),
    [write]
  );

  const remove = useCallback(
    async (ref: string) => {
      const done = await write(
        () => meetingsApi.deleteTemplate(ref),
        () => setTemplates(current => current.filter(item => item.ref !== ref))
      );
      return done !== null;
    },
    [write]
  );

  return {
    templates,
    maxUserTemplates,
    isLoading,
    isSaving,
    error,
    refetch,
    load,
    create,
    update,
    remove,
    bulkDuplicate,
    bulkDelete,
  };
}
