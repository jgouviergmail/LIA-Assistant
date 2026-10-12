'use client';

import dynamic from 'next/dynamic';
import { useState } from 'react';
import { usePathname } from 'next/navigation';
import { useEyesChatStore, RESTING_CHAT } from '@/stores/eyesChatStore';
import { CompanionPresence, isChatRoute } from '@/components/companion/CompanionPresence';
import { useAvatarStyleRollout } from '@/hooks/useAvatarStyleRollout';

const EyesWidget = dynamic(() => import('./EyesWidget').then(module => module.EyesWidget), {
  ssr: false,
});

/** One mount under the authenticated layout, preserved across all its pages. */
export function ApplicationEyes() {
  useAvatarStyleRollout();
  const onChat = isChatRoute(usePathname());
  const state = useEyesChatStore(store => store.state);
  const [backgroundWorking, setBackgroundWorking] = useState(false);
  const backgroundState = backgroundWorking
    ? { ...RESTING_CHAT, chatStatus: 'streaming' as const, streamPhase: 'progress' as const }
    : RESTING_CHAT;
  return (
    <>
      <CompanionPresence
        isAuthenticated
        renderAvatar={false}
        onWorkingChange={setBackgroundWorking}
      />
      <EyesWidget {...(onChat ? state : backgroundState)} dockToChat={onChat} />
    </>
  );
}
