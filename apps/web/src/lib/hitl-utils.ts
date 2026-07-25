/**
 * HITL (Human-in-the-Loop) Utilities
 * Generates conversational questions from action requests
 */

import type { TFunction } from 'i18next';
import { ActionRequest } from '@/types/chat';

/** Tool-name keywords per action category, in priority order (first match wins). */
const CATEGORY_KEYWORDS: Array<{ category: string; keywords: string[] }> = [
  { category: 'search', keywords: ['search', 'find', 'query'] },
  { category: 'delete', keywords: ['delete', 'remove'] },
  { category: 'create', keywords: ['create', 'add'] },
  { category: 'update', keywords: ['update', 'edit', 'modify', 'save'] },
  { category: 'send', keywords: ['send'] },
  { category: 'get', keywords: ['get', 'retrieve', 'fetch'] },
  { category: 'list', keywords: ['list'] },
];

/**
 * Categorize tool action type from tool name.
 * Returns the action category for i18n lookup.
 */
function getActionCategory(toolName: string): string {
  const name = toolName.toLowerCase();
  for (const { category, keywords } of CATEGORY_KEYWORDS) {
    if (keywords.some(kw => name.includes(kw))) {
      return category;
    }
  }
  return 'generic';
}

/** Which argument keys carry the human-readable target, per tool-name family. */
const TARGET_ARG_RULES: Array<{ match: (name: string) => boolean; keys: string[] }> = [
  { match: n => n.includes('search') || n.includes('find'), keys: ['query', 'search_query', 'q'] },
  { match: n => n.includes('contact'), keys: ['name', 'contact_name', 'given_name'] },
  { match: n => n.includes('send'), keys: ['to', 'recipient', 'email'] },
];
const GENERIC_TARGET_KEYS = ['name', 'target', 'id'];

/** First truthy string among ``keys`` (matches the original ``a || b || null`` semantics). */
function firstTruthyArg(args: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    if (args[key]) {
      return args[key] as string;
    }
  }
  return null;
}

/**
 * Extract target/query from action arguments.
 * Returns meaningful context from the tool arguments.
 */
function extractTarget(toolName: string, args: Record<string, unknown>): string | null {
  const name = toolName.toLowerCase();
  for (const rule of TARGET_ARG_RULES) {
    if (rule.match(name)) {
      return firstTruthyArg(args, rule.keys);
    }
  }
  return firstTruthyArg(args, GENERIC_TARGET_KEYS);
}

/**
 * Generate a fallback HITL question from action requests (template-based).
 *
 * This function is used as a fallback when backend LLM streaming fails or is unavailable.
 * Uses i18n translations to generate natural language questions based on action types.
 *
 * In production, the backend generates questions via LLM streaming for better quality.
 * This template-based approach ensures graceful degradation.
 *
 * @param actionRequests - Array of action requests from HITL interrupt
 * @param t - Translation function for i18n support
 * @returns Template-based question string in the user's language
 */
/** Single-action templates for categories that carry a target (key, default, i18n param name). */
const SINGLE_TARGET_TEMPLATES: Record<
  string,
  { withTarget: [string, string, string]; generic: [string, string] }
> = {
  search: {
    withTarget: [
      'hitl.search.with_query',
      'Do you confirm searching for contacts named "{{query}}"?',
      'query',
    ],
    generic: ['hitl.search.generic', 'Do you confirm this search?'],
  },
  delete: {
    withTarget: [
      'hitl.delete.with_target',
      '⚠️ Do you confirm deleting "{{target}}"? This action is irreversible.',
      'target',
    ],
    generic: ['hitl.delete.generic', '⚠️ Do you confirm this deletion? This action is irreversible.'],
  },
  create: {
    withTarget: ['hitl.create.with_target', 'Do you confirm creating "{{target}}"?', 'target'],
    generic: ['hitl.create.generic', 'Do you confirm this creation?'],
  },
  update: {
    withTarget: ['hitl.update.with_target', 'Do you confirm modifying "{{target}}"?', 'target'],
    generic: ['hitl.update.generic', 'Do you confirm this modification?'],
  },
  send: {
    withTarget: ['hitl.send.with_target', 'Do you confirm sending to "{{to}}"?', 'to'],
    generic: ['hitl.send.generic', 'Do you confirm this send?'],
  },
};

/** Single-action templates for categories with no target (key, default). */
const SINGLE_SIMPLE_TEMPLATES: Record<string, [string, string]> = {
  list: ['hitl.list', 'Do you confirm retrieving the list?'],
  get: ['hitl.get', 'Do you confirm retrieving this information?'],
};

/** Same-category multi-action templates (key, default; interpolates {{count}}). */
const MULTI_TEMPLATES: Record<string, [string, string]> = {
  delete: [
    'hitl.delete.multiple',
    '⚠️ Do you confirm deleting {{count}} items? This action is irreversible.',
  ],
  create: ['hitl.create.multiple', 'Do you confirm creating {{count}} items?'],
  update: ['hitl.update.multiple', 'Do you confirm modifying {{count}} items?'],
  send: ['hitl.send.multiple', 'Do you confirm sending {{count}} messages?'],
};

/** Build the confirmation question for a single action request. */
function singleActionQuestion(action: ActionRequest, t: TFunction): string {
  const category = getActionCategory(action.name);
  const target = extractTarget(action.name, action.args);

  const targetTpl = SINGLE_TARGET_TEMPLATES[category];
  if (targetTpl) {
    if (target) {
      const [key, def, param] = targetTpl.withTarget;
      return t(key, def, { [param]: target });
    }
    return t(targetTpl.generic[0], targetTpl.generic[1]);
  }

  const simpleTpl = SINGLE_SIMPLE_TEMPLATES[category];
  if (simpleTpl) {
    return t(simpleTpl[0], simpleTpl[1]);
  }

  // Generic fallback with a readable action name.
  const readableAction = action.name.replace(/_tool$/, '').replace(/_/g, ' ');
  return t('hitl.generic_action', 'Do you confirm executing "{{action}}"?', {
    action: readableAction,
  });
}

/** Build the confirmation question for several action requests. */
function multipleActionsQuestion(actionRequests: ActionRequest[], t: TFunction): string {
  const count = actionRequests.length;
  const uniqueCategories = [...new Set(actionRequests.map(a => getActionCategory(a.name)))];

  if (uniqueCategories.length === 1) {
    const tpl = MULTI_TEMPLATES[uniqueCategories[0]];
    if (tpl) {
      return t(tpl[0], tpl[1], { count });
    }
    return t('hitl.multiple_similar', 'Do you confirm executing {{count}} similar actions?', {
      count,
    });
  }

  // Mixed actions - generic plural.
  return t('hitl.multiple_actions', 'Do you confirm executing {{count}} actions?', { count });
}

export function generateFallbackHitlQuestion(
  actionRequests: ActionRequest[],
  t: TFunction
): string {
  if (!actionRequests || actionRequests.length === 0) {
    return t('hitl.default', 'Do you confirm this action?');
  }
  if (actionRequests.length === 1) {
    return singleActionQuestion(actionRequests[0], t);
  }
  return multipleActionsQuestion(actionRequests, t);
}

/**
 * Format action arguments for display.
 *
 * @param args - Action arguments object
 * @returns Formatted string representation
 */
export function formatActionArgs(args: Record<string, unknown>): string {
  try {
    return JSON.stringify(args, null, 2);
  } catch {
    return String(args);
  }
}

/**
 * Extract tool names from action requests.
 *
 * @param actionRequests - Array of action requests
 * @returns Array of tool names
 */
export function extractToolNames(actionRequests: ActionRequest[]): string[] {
  return actionRequests.map(action => action.name);
}
