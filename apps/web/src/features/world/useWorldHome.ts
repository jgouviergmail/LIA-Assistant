'use client';
import { homeViewSchema, type HomeView, type HomeWrite } from './home-protocol';
import { useWorldOwnerPreferences } from './useWorldOwnerPreferences';

export function useWorldHome(ownerId: string, enabled: boolean) {
  const { value, save, ...state } = useWorldOwnerPreferences<HomeView, HomeWrite>(
    ownerId,
    enabled,
    'home',
    homeViewSchema
  );
  return {
    ...state,
    home: value,
    save: async (payload: HomeWrite) => Boolean(await save(payload)),
  };
}
