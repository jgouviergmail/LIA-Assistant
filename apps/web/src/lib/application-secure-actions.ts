import type { ApplicationResource } from '@/lib/application-resources';

export interface SecureActionPresentation {
  title: string;
  completed?: string;
  committedFailure?: string;
  resource: ApplicationResource;
}

/** Reviewed browser completions; unknown operations never acquire a control. */
const actions = new Map<string, SecureActionPresentation>([
  ['device_sessions.revoke_others', { title: 'secure_title', resource: 'device_sessions' }],
  ['account_export.request', { title: 'secure_export_title', completed: 'secure_export_requested', committedFailure: 'secure_export_partial', resource: 'account_export' }],
]);

export function secureActionPresentation(operation: string) {
  return actions.get(operation);
}
