'use client';

/**
 * The minutes template library (ADR-259): every built-in plus the user's own.
 *
 * The list is loaded once; every write returns the server's row and updates
 * the list in place (a created template joins it, an updated one replaces its
 * summary, a removed one leaves). A failed write keeps the list and exposes
 * the error — the caller toasts.
 */

import { useCallback, useEffect, useRef } from 'react';

import { useStaleGuard } from '@/hooks/useStaleGuard';
import { useAuth } from '@/hooks/useAuth';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';
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
  const { user } = useAuth();
  const ownerId = user?.id;
  const { lifetime, isCurrent } = useApplicationAccountLifetime(ownerId);
  const [templates, setTemplates] = useApplicationAccountState<MeetingTemplateSummary[]>(ownerId, []);
  const [maxUserTemplates, setMaxUserTemplates] = useApplicationAccountState(ownerId, 0);
  const [isLoading, setIsLoading] = useApplicationAccountState(ownerId, enabled);
  const [isSaving, setIsSaving] = useApplicationAccountState(ownerId, false);
  const [error, setError] = useApplicationAccountState<Error | null>(ownerId, null);
  const guard = useStaleGuard();
  const pending = useRef<typeof lifetime | null>(null);

  const read = useCallback(async () => {
    if (!enabled || !isCurrent()) return false;
    const isStale = guard.begin();
    try {
      const library = await meetingsApi.templates();
      if (isStale() || !isCurrent()) return false;
      setTemplates(library.items);
      setMaxUserTemplates(library.max_user_templates);
      setError(null);
      return true;
    } catch (err) {
      if (isStale() || !isCurrent()) return false;
      setError(err instanceof Error ? err : new Error(String(err)));
      logger.error('meeting_templates_load_failed', err as Error, {
        component: 'useMeetingTemplates',
      });
      return false;
    } finally {
      if (!isStale() && isCurrent()) setIsLoading(false);
    }
  }, [enabled, guard, isCurrent, setTemplates, setMaxUserTemplates, setError, setIsLoading]);
  const refetch = useCallback(async () => { await read(); }, [read]);
  const refetchVerified = useCallback(async () => {
    if (!await read()) throw new Error('Meeting library refresh failed');
  }, [read]);
  useApplicationResourceSync(enabled ? ownerId : undefined, 'meeting_templates', refetchVerified);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  const write = useCallback(
    async <T>(operation: () => Promise<T>, apply: (result: T) => void): Promise<T | null> => {
      if (!enabled || !isCurrent() || pending.current === lifetime) return null;
      pending.current = lifetime;
      setIsSaving(true);
      try {
        const result = await operation();
        if (!isCurrent()) return null;
        apply(result);
        setError(null);
        return result;
      } catch (err) {
        if (isCurrent()) setError(err instanceof Error ? err : new Error(String(err)));
        return null;
      } finally {
        if (pending.current === lifetime) pending.current = null;
        if (isCurrent()) setIsSaving(false);
      }
    },
    [enabled, isCurrent, lifetime, setError, setIsSaving]
  );

  const load = useCallback(async (ref: string) => {
    if (!enabled || !isCurrent()) return null;
    try {
      const template = await meetingsApi.template(ref);
      return isCurrent() ? template : null;
    } catch (err) {
      if (isCurrent()) setError(err instanceof Error ? err : new Error(String(err)));
      return null;
    }
  }, [enabled, isCurrent, setError]);

  const create = useCallback(
    (request: MeetingTemplateCreate) =>
      write(
        () => meetingsApi.createTemplate(request),
        created => setTemplates(current => [...current.filter(item => item.ref !== created.ref), summaryOf(created)])
      ),
    [write, setTemplates]
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
    [write, setTemplates]
  );

  const bulkDuplicate = useCallback(
    (refs: string[]) =>
      write(
        () => meetingsApi.bulkDuplicateTemplates({ refs }),
        result => setTemplates(current => {
          const refs = new Set(result.created.map(item => item.ref));
          return [...current.filter(item => !refs.has(item.ref)), ...result.created];
        })
      ),
    [write, setTemplates]
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
    [write, setTemplates]
  );

  const remove = useCallback(
    async (ref: string) => {
      const done = await write(
        () => meetingsApi.deleteTemplate(ref),
        () => setTemplates(current => current.filter(item => item.ref !== ref))
      );
      return done !== null;
    },
    [write, setTemplates]
  );

  return {
    templates: enabled ? templates : [],
    maxUserTemplates: enabled ? maxUserTemplates : 0,
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
