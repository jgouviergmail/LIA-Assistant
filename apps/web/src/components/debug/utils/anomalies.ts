/**
 * Anomaly collection — the "identify the problem in 5 seconds" layer.
 *
 * One pure pass over a request's metrics returns every section carrying a
 * failure signal. The orchestrator surfaces the count on the request header
 * and a dot on each affected section trigger, so nothing has to be unfolded
 * to know WHERE to look.
 */

import { validateSectionSchemas } from '../validation/validators';
import type { DebugMetrics } from '@/types/chat';

export interface DebugAnomaly {
  /** Accordion value of the affected section. */
  section: string;
  /** Short human-readable description of the signal. */
  label: string;
}

/** One independent detection rule — small on purpose (CC ratchet). */
type AnomalyRule = (metrics: DebugMetrics) => DebugAnomaly[];

const plannerRule: AnomalyRule = metrics => {
  const planner = metrics.planner_intelligence;
  if (!planner) return [];
  const found: DebugAnomaly[] = [];
  if (!planner.success || planner.error) {
    found.push({ section: 'planner', label: planner.error || 'Planner failed' });
  }
  if (planner.flags.used_panic_mode) {
    found.push({ section: 'planner', label: 'Panic-mode planning' });
  }
  return found;
};

const failedStepsRule: AnomalyRule = metrics => {
  const failed = (metrics.execution_timeline?.steps ?? []).filter(s => s.success === false);
  if (failed.length === 0) return [];
  return [
    {
      section: 'execution',
      label: `${failed.length} step${failed.length > 1 ? 's' : ''} failed`,
    },
  ];
};

const validatorRule: AnomalyRule = metrics =>
  metrics.semantic_validation && !metrics.semantic_validation.is_valid
    ? [{ section: 'semantic_validation', label: 'Validator rejected the plan (informative)' }]
    : [];

const tokenZoneRule: AnomalyRule = metrics => {
  const zone = metrics.token_budget?.zone;
  return zone === 'critical' || zone === 'emergency'
    ? [{ section: 'token_budget', label: `Token budget in ${zone} zone` }]
    : [];
};

const reactCeilingRule: AnomalyRule = metrics => {
  const react = metrics.react_execution;
  return react && react.max_iterations > 0 && react.iterations >= react.max_iterations
    ? [{ section: 'react_execution', label: 'ReAct loop hit its iteration ceiling' }]
    : [];
};

const sectionErrorsRule: AnomalyRule = metrics => {
  const errors: [string, string | undefined][] = [
    ['knowledge-enrichment', metrics.knowledge_enrichment?.error],
    ['memory-detection', metrics.memory_detection?.error],
    ['interest-profile', metrics.interest_profile?.error],
  ];
  return errors
    .filter((entry): entry is [string, string] => Boolean(entry[1]))
    .map(([section, label]) => ({ section, label }));
};

const RULES: AnomalyRule[] = [
  plannerRule,
  failedStepsRule,
  validatorRule,
  tokenZoneRule,
  reactCeilingRule,
  sectionErrorsRule,
  // Zod as a DETECTOR: a section whose payload drifted from its schema is
  // itself an anomaly worth surfacing — never a reason to hide the section.
  validateSectionSchemas,
];

/** Collect every failure signal present in one request's metrics. */
export function collectAnomalies(metrics: DebugMetrics): DebugAnomaly[] {
  return RULES.flatMap(rule => rule(metrics));
}
