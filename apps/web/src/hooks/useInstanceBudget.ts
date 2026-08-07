/**
 * Instance-wide daily spend ceiling: load, edit, save.
 *
 * Per-user limits bound what ONE account consumes; this bounds what the whole
 * deployment spends in a UTC day — the only protection that holds when every
 * visitor gets their own account.
 *
 * The state lives here so the card stays a rendering concern (the repo's
 * complexity ratchet counts decision points per function, and a component
 * that both fetches and validates crosses it).
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { apiClient, ApiError } from '@/lib/api-client';
import { logger } from '@/lib/logger';

/** Admin endpoint carrying both configured bounds and today's consumption. */
export const INSTANCE_BUDGET_ENDPOINT = '/usage-limits/admin/instance-daily-budget';

export interface InstanceBudgetResponse {
  /** Operator ceiling in euros; null when unset. */
  ceiling_eur: string | null;
  /** Deployment ceiling from the environment; null when unset. */
  deployment_ceiling_eur: string | null;
  /** What the runtime enforces: the smallest configured bound. */
  effective_ceiling_eur: string | null;
  /** Spend already charged to the current UTC day. */
  spent_today_eur: string;
  /** Runs charged to the current UTC day. */
  runs_today: number;
  is_default: boolean;
}

/** A draft that may be saved, or the reason it may not. */
export type CeilingDraft = { valid: true; value: string | null } | { valid: false };

/**
 * Validate a typed ceiling.
 *
 * An emptied field is a real action — remove the operator ceiling — not an
 * error. Zero or negative is refused: "allow nothing" is expressed by
 * disabling the feature, not by a bound nobody can satisfy.
 */
export function parseCeilingDraft(draft: string): CeilingDraft {
  const trimmed = draft.trim();
  if (trimmed === '') return { valid: true, value: null };
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed) || parsed <= 0) return { valid: false };
  return { valid: true, value: trimmed };
}

export interface UseInstanceBudgetReturn {
  data: InstanceBudgetResponse | null;
  draft: string;
  setDraft: (value: string) => void;
  error: string | null;
  saving: boolean;
  save: () => Promise<void>;
}

/** Load the ceiling, hold the edit draft, save it. */
export function useInstanceBudget(): UseInstanceBudgetReturn {
  const { t } = useTranslation();

  const [data, setData] = useState<InstanceBudgetResponse | null>(null);
  const [draft, setDraft] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const apply = useCallback((response: InstanceBudgetResponse) => {
    setData(response);
    setDraft(response.ceiling_eur ?? '');
  }, []);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .get<InstanceBudgetResponse>(INSTANCE_BUDGET_ENDPOINT)
      .then(response => {
        if (!cancelled) apply(response);
      })
      .catch((err: unknown) => {
        logger.error('instance_budget_fetch_failed', err as Error, {
          component: 'useInstanceBudget',
        });
      });
    return () => {
      cancelled = true;
    };
  }, [apply]);

  const save = useCallback(async () => {
    const parsed = parseCeilingDraft(draft);
    if (!parsed.valid) {
      setError(t('usage_limits.instance_budget.invalid'));
      return;
    }
    setError(null);
    setSaving(true);
    try {
      const response = await apiClient.put<InstanceBudgetResponse>(INSTANCE_BUDGET_ENDPOINT, {
        ceiling_eur: parsed.value,
      });
      apply(response);
      toast.success(t('usage_limits.instance_budget.saved'));
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : t('usage_limits.instance_budget.save_failed');
      toast.error(message);
      logger.error('instance_budget_save_failed', err as Error, {
        component: 'useInstanceBudget',
      });
    } finally {
      setSaving(false);
    }
  }, [apply, draft, t]);

  return { data, draft, setDraft, error, saving, save };
}
