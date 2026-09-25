/**
 * Which model a call ran on, as the debug panel names it (B8, 2026-09-24).
 *
 * A call carries two names: the one the request NAMED — the slot's
 * configuration, what the admin screen shows — and the one the provider
 * ANSWERED under, which is what is billed. They differ when a provider resolves
 * an alias or answers under a dated snapshot; the panel used to show only the
 * second, i.e. a model nobody configured. The configured name leads; the served
 * one follows only when it differs.
 */

import type { LLMCall } from '@/types/chat';

export interface CallModel {
  /** The configured model, else — no request name recorded — the reported one. */
  name: string;
  /** The provider's own name for it, only when it differs from `name`. */
  servedAs: string | null;
}

/** What a failed call reports: no model at all. Never a « served » name. */
const UNREPORTED = 'unknown';

export function callModel(call: Pick<LLMCall, 'model_name' | 'requested_model'>): CallModel {
  const requested = call.requested_model?.trim();
  if (!requested) return { name: call.model_name, servedAs: null };
  const served = call.model_name;
  const differs = Boolean(served) && served !== requested && served !== UNREPORTED;
  return { name: requested, servedAs: differs ? served : null };
}

/** `name (served as …)`, the tooltip form. */
export function callModelTitle(model: CallModel): string {
  return model.servedAs ? `${model.name} (served as ${model.servedAs})` : model.name;
}
