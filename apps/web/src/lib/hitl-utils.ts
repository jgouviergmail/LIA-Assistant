/**
 * HITL (Human-in-the-Loop) Utilities
 * Generates conversational questions from action requests
 */

import type { TFunction } from 'i18next';
import { ActionRequest } from '@/types/chat';

/**
 * Categorize tool action type from tool name.
 * Returns the action category for i18n lookup.
 */
function getActionCategory(toolName: string): string {
  const name = toolName.toLowerCase();

  if (name.includes('search') || name.includes('find') || name.includes('query')) {
    return 'search';
  }
  if (name.includes('delete') || name.includes('remove')) {
    return 'delete';
  }
  if (name.includes('create') || name.includes('add')) {
    return 'create';
  }
  if (
    name.includes('update') ||
    name.includes('edit') ||
    name.includes('modify') ||
    name.includes('save')
  ) {
    return 'update';
  }
  if (name.includes('send')) {
    return 'send';
  }
  if (name.includes('get') || name.includes('retrieve') || name.includes('fetch')) {
    return 'get';
  }
  if (name.includes('list')) {
    return 'list';
  }

  return 'generic';
}

/**
 * Extract target/query from action arguments.
 * Returns meaningful context from the tool arguments.
 */
function extractTarget(toolName: string, args: Record<string, unknown>): string | null {
  const name = toolName.toLowerCase();

  // Search operations - extract query
  if (name.includes('search') || name.includes('find')) {
    return (args.query || args.search_query || args.q || null) as string | null;
  }

  // Contact operations - extract name
  if (name.includes('contact')) {
    return (args.name || args.contact_name || args.given_name || null) as string | null;
  }

  // Send operations - extract recipient
  if (name.includes('send')) {
    return (args.to || args.recipient || args.email || null) as string | null;
  }

  // Generic name/target
  return (args.name || args.target || args.id || null) as string | null;
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
export function generateFallbackHitlQuestion(
  actionRequests: ActionRequest[],
  t: TFunction
): string {
  if (!actionRequests || actionRequests.length === 0) {
    return t('hitl.default', 'Do you confirm this action?');
  }

  // Single action request - use i18n templates
  if (actionRequests.length === 1) {
    const action = actionRequests[0];
    const category = getActionCategory(action.name);
    const target = extractTarget(action.name, action.args);

    // Use specific i18n key based on category and whether we have a target
    if (category === 'search' && target) {
      return t(
        'hitl.search.with_query',
        'Do you confirm searching for contacts named "{{query}}"?',
        { query: target }
      );
    }
    if (category === 'search') {
      return t('hitl.search.generic', 'Do you confirm this search?');
    }

    if (category === 'delete' && target) {
      return t(
        'hitl.delete.with_target',
        '⚠️ Do you confirm deleting "{{target}}"? This action is irreversible.',
        { target }
      );
    }
    if (category === 'delete') {
      return t(
        'hitl.delete.generic',
        '⚠️ Do you confirm this deletion? This action is irreversible.'
      );
    }

    if (category === 'create' && target) {
      return t('hitl.create.with_target', 'Do you confirm creating "{{target}}"?', { target });
    }
    if (category === 'create') {
      return t('hitl.create.generic', 'Do you confirm this creation?');
    }

    if (category === 'update' && target) {
      return t('hitl.update.with_target', 'Do you confirm modifying "{{target}}"?', { target });
    }
    if (category === 'update') {
      return t('hitl.update.generic', 'Do you confirm this modification?');
    }

    if (category === 'send' && target) {
      return t('hitl.send.with_target', 'Do you confirm sending to "{{to}}"?', { to: target });
    }
    if (category === 'send') {
      return t('hitl.send.generic', 'Do you confirm this send?');
    }

    if (category === 'list') {
      return t('hitl.list', 'Do you confirm retrieving the list?');
    }

    if (category === 'get') {
      return t('hitl.get', 'Do you confirm retrieving this information?');
    }

    // Generic fallback with action name
    const readableAction = action.name.replace(/_tool$/, '').replace(/_/g, ' ');
    return t('hitl.generic_action', 'Do you confirm executing "{{action}}"?', {
      action: readableAction,
    });
  }

  // Multiple action requests
  const count = actionRequests.length;

  // Check if all actions are of the same category
  const categories = actionRequests.map(a => getActionCategory(a.name));
  const uniqueCategories = [...new Set(categories)];

  if (uniqueCategories.length === 1) {
    const category = uniqueCategories[0];

    if (category === 'delete') {
      return t(
        'hitl.delete.multiple',
        '⚠️ Do you confirm deleting {{count}} items? This action is irreversible.',
        { count }
      );
    }
    if (category === 'create') {
      return t('hitl.create.multiple', 'Do you confirm creating {{count}} items?', { count });
    }
    if (category === 'update') {
      return t('hitl.update.multiple', 'Do you confirm modifying {{count}} items?', { count });
    }
    if (category === 'send') {
      return t('hitl.send.multiple', 'Do you confirm sending {{count}} messages?', { count });
    }

    return t('hitl.multiple_similar', 'Do you confirm executing {{count}} similar actions?', {
      count,
    });
  }

  // Mixed actions - generic plural
  return t('hitl.multiple_actions', 'Do you confirm executing {{count}} actions?', { count });
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
