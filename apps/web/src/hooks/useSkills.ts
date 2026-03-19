import { useCallback } from 'react';
import { useApiQuery } from './useApiQuery';
import { useApiMutation } from './useApiMutation';

/**
 * Skill from the API (L1 safe subset — no instructions).
 */
export interface Skill {
  name: string;
  description: string;
  /** Localized descriptions keyed by language code (fr, en, es, de, it, zh). null if not yet translated. */
  descriptions: Record<string, string> | null;
  scope: 'admin' | 'user';
  category: string | null;
  priority: number;
  always_loaded: boolean;
  has_scripts: boolean;
  has_plan_template: boolean;
  /** Per-user toggle (personal preference). */
  enabled_for_user: boolean;
  /** System-level toggle (admin only). True = available to users, false = hidden. */
  admin_enabled?: boolean;
}

/**
 * API list response shape.
 */
interface SkillListResponse {
  skills: Skill[];
  total: number;
}

/**
 * Reload response shape.
 */
interface SkillReloadResponse {
  count: number;
}

/**
 * Toggle response shape (per-user preference).
 */
interface SkillToggleResponse {
  skill_name: string;
  enabled_for_user: boolean;
}

/**
 * Admin system-toggle response shape.
 */
interface AdminSystemToggleResponse {
  skill_name: string;
  admin_enabled: boolean;
}

const ENDPOINT = '/skills';

/**
 * Hook for skills CRUD operations.
 *
 * @param adminView - If true, fetches from /skills/admin/list (all system skills
 *   with admin_enabled flag). Used by AdminSkillsSection only.
 */
export function useSkills(adminView = false) {
  const listEndpoint = adminView ? `${ENDPOINT}/admin/list` : ENDPOINT;
  const {
    data: listData,
    loading,
    error,
    refetch,
    setData,
  } = useApiQuery<SkillListResponse>(listEndpoint, {
    componentName: 'Skills',
    initialData: { skills: [], total: 0 },
  });

  const skills = listData?.skills ?? [];
  const total = listData?.total ?? 0;

  // Mutations
  const deleteMutation = useApiMutation<void, void>({
    method: 'DELETE',
    componentName: 'Skills',
  });

  const reloadMutation = useApiMutation<void, SkillReloadResponse>({
    method: 'POST',
    componentName: 'Skills',
  });

  const toggleMutation = useApiMutation<void, SkillToggleResponse>({
    method: 'PATCH',
    componentName: 'Skills',
  });

  const adminSystemToggleMutation = useApiMutation<void, AdminSystemToggleResponse>({
    method: 'PATCH',
    componentName: 'Skills',
  });

  /**
   * Import a skill via FormData upload.
   * Uses raw fetch because apiClient forces Content-Type: application/json.
   */
  const uploadSkill = useCallback(
    async (file: File, endpoint: string): Promise<Skill | undefined> => {
      const formData = new FormData();
      formData.append('file', file);

      const apiUrl = process.env.NEXT_PUBLIC_API_URL || '';
      const baseUrl = apiUrl ? `${apiUrl}/api/v1` : '/api/v1';

      const response = await fetch(`${baseUrl}${endpoint}`, {
        method: 'POST',
        credentials: 'include',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(errorData?.detail || `Import failed (${response.status})`);
      }

      const result: Skill = await response.json();

      // Optimistic: add or replace in list (handles re-import of same name)
      setData(prev => {
        if (!prev) return prev;
        const existing = prev.skills.some(s => s.name === result.name);
        return {
          skills: existing
            ? prev.skills.map(s => (s.name === result.name ? result : s))
            : [...prev.skills, result],
          total: existing ? prev.total : prev.total + 1,
        };
      });

      return result;
    },
    [setData]
  );

  /** Import a SKILL.md or .zip to the user's skill directory. */
  const importSkill = useCallback(
    (file: File) => uploadSkill(file, `${ENDPOINT}/import`),
    [uploadSkill]
  );

  /** Import a SKILL.md or .zip to the system (admin) skill directory. */
  const importAdminSkill = useCallback(
    (file: File) => uploadSkill(file, `${ENDPOINT}/admin/import`),
    [uploadSkill]
  );

  const deleteSkill = useCallback(
    async (skillName: string) => {
      await deleteMutation.mutate(`${ENDPOINT}/${skillName}`);
      // Optimistic: remove from list
      setData(prev => {
        if (!prev) return prev;
        return {
          skills: prev.skills.filter(s => s.name !== skillName),
          total: prev.total - 1,
        };
      });
    },
    [deleteMutation, setData]
  );

  const toggleSkill = useCallback(
    async (skillName: string) => {
      const result = await toggleMutation.mutate(`${ENDPOINT}/${skillName}/toggle`);
      if (result) {
        // Optimistic: update enabled_for_user (personal preference)
        setData(prev => {
          if (!prev) return prev;
          return {
            ...prev,
            skills: prev.skills.map(s =>
              s.name === skillName ? { ...s, enabled_for_user: result.enabled_for_user } : s
            ),
          };
        });
      }
      return result;
    },
    [toggleMutation, setData]
  );

  /** System-level toggle for admin skills (superuser only). */
  const adminSystemToggleSkill = useCallback(
    async (skillName: string) => {
      const result = await adminSystemToggleMutation.mutate(
        `${ENDPOINT}/admin/${skillName}/system-toggle`
      );
      if (result) {
        // Optimistic: update admin_enabled (system-level toggle)
        setData(prev => {
          if (!prev) return prev;
          return {
            ...prev,
            skills: prev.skills.map(s =>
              s.name === skillName ? { ...s, admin_enabled: result.admin_enabled } : s
            ),
          };
        });
      }
      return result;
    },
    [adminSystemToggleMutation, setData]
  );

  const reloadSkills = useCallback(async () => {
    const result = await reloadMutation.mutate(`${ENDPOINT}/reload`);
    if (result) {
      await refetch();
    }
    return result;
  }, [reloadMutation, refetch]);

  const translateMutation = useApiMutation<
    void,
    { skill_name: string; descriptions: Record<string, string> }
  >({
    method: 'POST',
    componentName: 'Skills',
  });

  const updateDescriptionMutation = useApiMutation<
    { description: string; source_language: string },
    { skill_name: string; descriptions: Record<string, string> }
  >({
    method: 'PATCH',
    componentName: 'Skills',
  });

  const deleteAdminMutation = useApiMutation<void, void>({
    method: 'DELETE',
    componentName: 'Skills',
  });

  const translateSkillDescription = useCallback(
    async (skillName: string) => {
      const result = await translateMutation.mutate(
        `${ENDPOINT}/admin/${skillName}/translate-description`
      );
      if (result) {
        setData(prev => {
          if (!prev) return prev;
          return {
            ...prev,
            skills: prev.skills.map(s =>
              s.name === skillName ? { ...s, descriptions: result.descriptions } : s
            ),
          };
        });
      }
      return result;
    },
    [translateMutation, setData]
  );

  /** Update admin skill description (any language) → auto-translate → reload. */
  const updateAdminSkillDescription = useCallback(
    async (skillName: string, description: string, sourceLang: string) => {
      const result = await updateDescriptionMutation.mutate(
        `${ENDPOINT}/admin/${skillName}/description`,
        { description, source_language: sourceLang }
      );
      if (result) {
        setData(prev => {
          if (!prev) return prev;
          return {
            ...prev,
            skills: prev.skills.map(s =>
              s.name === skillName ? { ...s, descriptions: result.descriptions } : s
            ),
          };
        });
      }
      return result;
    },
    [updateDescriptionMutation, setData]
  );

  /** Download any accessible skill as a zip archive (browser download). */
  const downloadSkill = useCallback(async (skillName: string, isAdmin = false) => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || '';
    const baseUrl = apiUrl ? `${apiUrl}/api/v1` : '/api/v1';
    const endpoint = isAdmin
      ? `${baseUrl}${ENDPOINT}/admin/${skillName}/download`
      : `${baseUrl}${ENDPOINT}/${skillName}/download`;

    const response = await fetch(endpoint, { credentials: 'include' });
    if (!response.ok) {
      throw new Error(`Download failed (${response.status})`);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${skillName}.zip`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, []);

  /** Delete an admin (system) skill — superuser only. */
  const deleteAdminSkill = useCallback(
    async (skillName: string) => {
      await deleteAdminMutation.mutate(`${ENDPOINT}/admin/${skillName}`);
      setData(prev => {
        if (!prev) return prev;
        return {
          skills: prev.skills.filter(s => s.name !== skillName),
          total: prev.total - 1,
        };
      });
    },
    [deleteAdminMutation, setData]
  );

  return {
    // Data
    skills,
    total,
    loading,
    error,
    refetch,

    // Mutations
    importSkill,
    importAdminSkill,
    deleteSkill,
    deleteAdminSkill,
    toggleSkill,
    adminSystemToggleSkill,
    reloadSkills,
    translateSkillDescription,
    updateAdminSkillDescription,
    downloadSkill,

    // Mutation states
    deleting: deleteMutation.loading,
    deletingAdmin: deleteAdminMutation.loading,
    toggling: toggleMutation.loading,
    togglingSystem: adminSystemToggleMutation.loading,
    reloading: reloadMutation.loading,
    translating: translateMutation.loading,
    updatingDescription: updateDescriptionMutation.loading,
  };
}
