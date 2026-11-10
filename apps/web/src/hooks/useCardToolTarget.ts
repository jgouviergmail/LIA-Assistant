'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { useDashboardRoute } from '@/components/dashboard/DashboardNavigation';
import { homeLanguage } from '@/lib/briefing-tools';
import { resolveCardTarget, cardToolHref, type CardTargetKind } from '@/lib/workbench/card-target';
import { useApiMutation } from './useApiMutation';

type State = 'idle' | 'opening' | 'historical' | 'source_changed' | 'unavailable' | 'error';

/** One explicit click, one abortable source check; no provider request on render. */
export function useCardToolTarget(token: string | null, kind: CardTargetKind, offered: boolean) {
  const { i18n } = useTranslation();
  const language = homeLanguage(i18n?.language);
  const router = useRouter();
  const navigate = useDashboardRoute(router.push);
  const { mutate } = useApiMutation<{ token: string }, unknown>({
    method: 'POST',
    componentName: 'CardToolTarget',
    retainResponse: false,
  });
  const pending = useRef<AbortController | null>(null);
  const [attempt, setAttempt] = useState<{ token: string | null; offered: boolean; state: State }>({
    token,
    offered,
    state: 'idle',
  });
  const current = attempt.token === token && attempt.offered === offered;
  // Prop transitions retire their old attempt before children render, including off → on.
  if (!current) setAttempt({ token, offered, state: 'idle' });
  const state = current ? attempt.state : 'idle';
  useEffect(
    () => () => {
      pending.current?.abort();
      pending.current = null;
    },
    [token, offered]
  );
  const open = useCallback(async () => {
    if (!offered || pending.current) return;
    if (!token) {
      setAttempt({ token, offered, state: 'historical' });
      return;
    }
    const controller = new AbortController();
    pending.current = controller;
    setAttempt({ token, offered, state: 'opening' });
    try {
      const response = await mutate(
        '/workbench/card-target',
        { token },
        { signal: controller.signal }
      );
      if (controller.signal.aborted) return;
      const { href, reason } = resolveCardTarget(response, language, token);
      if (href) {
        setAttempt({ token, offered, state: 'idle' });
        navigate(href);
      } else {
        setAttempt({ token, offered, state: reason });
      }
    } catch {
      if (!controller.signal.aborted) setAttempt({ token, offered, state: 'error' });
    } finally {
      if (pending.current === controller) pending.current = null;
    }
  }, [language, mutate, navigate, token, offered]);
  return {
    state,
    open,
    openTool: () => {
      if (offered) navigate(cardToolHref(kind, language));
    },
  };
}
