'use client';

import { createContext, useContext, type ReactNode } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useIconStylePreference, type IconStylePreference } from '@/hooks/useIconStylePreference';
import type { User } from '@/lib/auth';
import { DEFAULT_ICON_STYLE, type IconStyleUpdate } from '@/lib/icon-style';
import { IconStyleContext } from '@/lib/icon-style-context';

const PreferenceContext = createContext<IconStylePreference>({
  style: DEFAULT_ICON_STYLE,
  saving: false,
  failed: false,
  selectStyle: () => {},
  retry: () => {},
});

function AccountIconStyleProvider({
  user,
  applyUserUpdate,
  children,
}: {
  user: User | null;
  applyUserUpdate: (updated: IconStyleUpdate) => boolean;
  children: ReactNode;
}) {
  const preference = useIconStylePreference(user, applyUserUpdate);
  return (
    <PreferenceContext.Provider value={preference}>
      <IconStyleContext.Provider value={preference.style}>{children}</IconStyleContext.Provider>
    </PreferenceContext.Provider>
  );
}

/** The account key prevents any optimistic preference leaking across sign-ins. */
export function IconStyleProvider({ children }: { children: ReactNode }) {
  const { user, applyUserUpdate } = useAuth();
  return (
    <AccountIconStyleProvider
      key={user?.id ?? 'anonymous'}
      user={user}
      applyUserUpdate={applyUserUpdate}
    >
      {children}
    </AccountIconStyleProvider>
  );
}

export function useIconStyleSettings(): IconStylePreference {
  return useContext(PreferenceContext);
}
