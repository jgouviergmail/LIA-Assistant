'use client';
import { useMemo, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { Skeleton } from '@/components/ui/skeleton';
import { useAuth } from '@/hooks/useAuth';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { WorldWorkspace } from './activity-catalogue';
import { workspaceAvailable } from './activity-entry';

function WorkspaceSkeleton() {
  return <Skeleton className="h-48 w-full" />;
}
const Relations = dynamic(
  () => import('@/components/relations/RelationsWorkspace').then(m => m.RelationsWorkspace),
  { loading: WorkspaceSkeleton }
);
const Workboard = dynamic(
  () => import('@/components/workboard/WorkboardPage').then(m => m.WorkboardPage),
  { loading: WorkspaceSkeleton }
);
const Meetings = dynamic(
  () => import('@/components/meetings/MeetingsWorkspace').then(m => m.MeetingsWorkspace),
  { loading: WorkspaceSkeleton }
);
const Meeting = dynamic(
  () => import('@/components/meetings/MeetingDetailWorkspace').then(m => m.MeetingDetailWorkspace),
  { loading: WorkspaceSkeleton }
);
const Alerts = dynamic(
  () => import('@/components/notifications/NotificationsHub').then(m => m.NotificationsHub),
  { loading: WorkspaceSkeleton }
);
const Registers = dynamic(
  () => import('@/components/effects/RegistersPage').then(m => m.RegistersPage),
  { loading: WorkspaceSkeleton }
);
const Sms = dynamic(() => import('@/components/sms/SmsArchive').then(m => m.SmsArchive), {
  loading: WorkspaceSkeleton,
});

export function WorldWorkspacePanel({
  lng,
  ownerId,
  workspace,
  onNavigate,
  onCompose,
  initialMeetingId,
}: {
  lng: Language;
  ownerId: string;
  workspace: WorldWorkspace;
  initialMeetingId?: string;
  onNavigate: (workspace: WorldWorkspace) => void;
  onCompose: () => void;
}) {
  const { user } = useAuth();
  const { config } = useAppConfig();
  const { t } = useTranslation(lng);
  const scroll = useRef<HTMLDivElement>(null);
  const scrollPort = useMemo(
    () => ({
      read: () => scroll.current?.scrollTop ?? 0,
      write: (top: number) => {
        const element = scroll.current;
        if (element) element.scrollTop = top;
      },
    }),
    []
  );
  if (user?.id !== ownerId || !user.is_active) return null;
  if (!workspaceAvailable(workspace, config))
    return <p role="status">{t('world.functions.unavailable')}</p>;
  let content;
  switch (workspace) {
    case 'relations':
      content = <Relations lng={lng} scrollPort={scrollPort} />;
      break;
    case 'workboard':
      content = <Workboard lng={lng} embedded />;
      break;
    case 'meetings':
      content = (
        <WorldMeetings
          key={initialMeetingId ?? 'list'}
          lng={lng}
          onCompose={onCompose}
          initialMeetingId={initialMeetingId}
        />
      );
      break;
    case 'alerts':
      content = <Alerts lng={lng} onOpenJournal={() => onNavigate('registers')} />;
      break;
    case 'registers':
      content = <Registers lng={lng} />;
      break;
    case 'sms':
      content = <Sms lng={lng} />;
      break;
  }
  return (
    <div ref={scroll} className="h-full overflow-y-auto p-1">
      {content}
    </div>
  );
}

function WorldMeetings({
  lng,
  onCompose,
  initialMeetingId,
}: {
  lng: Language;
  onCompose: () => void;
  initialMeetingId?: string;
}) {
  const [selected, setSelected] = useState<string | null>(initialMeetingId ?? null);
  const opener = useRef<HTMLElement | null>(null);
  const open = (id: string) => {
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setSelected(id);
  };
  const back = () => {
    setSelected(null);
    requestAnimationFrame(() => {
      if (opener.current?.isConnected) opener.current.focus({ preventScroll: true });
    });
  };
  return (
    <>
      <div hidden={selected !== null}>
        <Meetings
          lng={lng}
          embedded
          active={selected === null}
          onOpenMeeting={open}
          onEmptyAction={onCompose}
        />
      </div>
      {selected && (
        <Meeting key={selected} lng={lng} id={selected} onBack={back} onOpenMeeting={setSelected} />
      )}
    </>
  );
}
