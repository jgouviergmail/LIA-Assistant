'use client';

/**
 * Compact history of the user's recent agentic calls (GET /telephony/calls).
 *
 * Shows only status + summary — never the callee's phone number (the API omits
 * it). Rendered inside the connected-telephony accordion.
 */

import { Loader2, Phone } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { Language } from '@/i18n/settings';
import { useApiQuery } from '@/hooks/useApiQuery';

interface TelephonyCall {
  id: string;
  callee_display: string;
  objective: string;
  status: string;
  outcome?: string | null;
  summary?: string | null;
  call_seconds?: number | null;
  created_at: string;
  completed_at?: string | null;
}

const STATUS_COLOR: Record<string, string> = {
  completed: 'text-green-600 dark:text-green-400',
  dialing: 'text-indigo-500',
  in_progress: 'text-indigo-500',
  voicemail: 'text-amber-600 dark:text-amber-400',
  no_answer: 'text-amber-600 dark:text-amber-400',
  failed: 'text-red-600 dark:text-red-400',
  cancelled: 'text-gray-500',
};

export function TelephonyCallHistory({ lng }: { lng: Language }) {
  const { t } = useTranslation();
  const { data, loading } = useApiQuery<TelephonyCall[]>('/telephony/calls', {
    componentName: 'TelephonyCallHistory',
    params: { limit: 10 },
  });

  if (loading) {
    return (
      <div className="flex justify-center py-3">
        <Loader2 className="h-4 w-4 animate-spin text-gray-400" />
      </div>
    );
  }

  const calls = data ?? [];
  if (calls.length === 0) {
    return (
      <p className="py-2 text-center text-xs text-gray-500">
        {t('settings.connectors.telephony.no_calls')}
      </p>
    );
  }

  return (
    <div className="space-y-2">
      <h5 className="text-xs font-medium text-gray-500">
        {t('settings.connectors.telephony.recent_calls')}
      </h5>
      {calls.map(call => (
        <div
          key={call.id}
          className="rounded-lg border border-gray-200 p-2 text-xs dark:border-gray-700"
        >
          <div className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-1.5 font-medium">
              <Phone className="h-3.5 w-3.5 text-indigo-500" />
              {call.callee_display}
            </span>
            <span className={STATUS_COLOR[call.status] ?? 'text-gray-500'}>
              {t(`settings.connectors.telephony.call_status.${call.status}`)}
            </span>
          </div>
          {call.summary && <p className="mt-1 text-gray-600 dark:text-gray-400">{call.summary}</p>}
          <p className="mt-1 text-gray-400">
            {new Date(call.created_at).toLocaleString(lng, {
              dateStyle: 'short',
              timeStyle: 'short',
            })}
          </p>
        </div>
      ))}
    </div>
  );
}
