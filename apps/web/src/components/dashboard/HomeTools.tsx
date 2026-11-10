'use client';

/**
 * What the home's cards may do through the « Tools » (owner, 2026-11-07).
 *
 * Where the instance offers the Tools, an item opens in its tool and a direct act calls the tool's
 * own route — the person's act, no model, no register row (ADR-369, D5). The operator's switch
 * keeps the chat (the demonstrator). A card's data already says its own provider answers, so its
 * items open on the instance's verdict alone; what a card hands to ANOTHER tool (a file to a new
 * message, an SMS's sender to the contacts) waits for the read of `GET /workbench` — the rail's
 * own, shared with the section — to say that tool is connected.
 *
 * Read ONCE for the whole home by the dashboard (`HomeToolsProvider`); a card rendered outside it
 * reads « the chat only », exactly what the home did before.
 */
import { useRouter } from 'next/navigation';
import { createContext, useContext, useMemo, type ReactNode } from 'react';

import type { AppConfig } from '@/hooks/useAppConfig';
import { useAuth } from '@/hooks/useAuth';
import { useWorkbenchAvailability } from '@/hooks/useWorkbenchAvailability';
import type { Language } from '@/i18n/settings';
import { workbenchAvailable } from '@/lib/workbench/availability';
import { HANDOFF_TOOLS, type HandoffKind, type WorkbenchHandoff } from '@/lib/workbench/handoff';
import { useHandoffNavigation } from '@/hooks/useHandoff';

import { useDashboardRoute } from './DashboardNavigation';

export interface HomeTools {
  /** The instance offers the Tools: an item opens in its tool, a direct act calls its route. */
  offered: boolean;
  /** Whether what a card hands over has a connected tool to go to. */
  offers: (kind: HandoffKind) => boolean;
  /** Opens that tool on it. */
  go: (handoff: WorkbenchHandoff) => void;
  /** The account's zone: « tomorrow » and a reminder's moments are read on its clock. */
  zone: string | undefined;
}

/** Outside the dashboard: the chat only. */
const CHAT_ONLY: HomeTools = {
  offered: false,
  offers: () => false,
  go: () => undefined,
  zone: undefined,
};

const HomeToolsContext = createContext<HomeTools>(CHAT_ONLY);

export function HomeToolsProvider({
  lng,
  config,
  children,
}: {
  lng: Language;
  /** The dashboard's current configuration, including its initial layout seed. */
  config: AppConfig | null;
  children: ReactNode;
}) {
  const { user } = useAuth();
  const offered = workbenchAvailable(config);
  const { availability } = useWorkbenchAvailability(offered);
  const router = useRouter();
  const navigate = useDashboardRoute(router.push);
  const zone = user?.timezone;
  const go = useHandoffNavigation(lng, navigate);
  const tools = useMemo<HomeTools>(
    () => ({
      offered,
      offers: kind =>
        offered &&
        (availability?.tools.some(
          item => item.tool === HANDOFF_TOOLS[kind] && item.state === 'ready'
        ) ??
          false),
      go,
      zone,
    }),
    [offered, availability, go, zone]
  );
  return <HomeToolsContext value={tools}>{children}</HomeToolsContext>;
}

/** @returns What the home's cards may do through the Tools; the chat only outside the home. */
export function useHomeTools(): HomeTools {
  return useContext(HomeToolsContext);
}
