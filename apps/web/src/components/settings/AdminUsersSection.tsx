'use client';

import { useState, useEffect, useCallback, useOptimistic, useTransition } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { SearchInput } from '@/components/ui/search-input';
import { Pagination } from '@/components/ui/pagination';
import { TableSkeleton } from '@/components/ui/skeleton';
import {
  Volume2,
  VolumeOff,
  Brain,
  Eye,
  EyeOff,
  Plug,
  Bookmark,
  Users,
  Sparkles,
} from 'lucide-react';
import apiClient from '@/lib/api-client';
import { ADMIN_USERS_PAGE_SIZE, SEARCH_DEBOUNCE_MS } from '@/lib/constants';
import { logger } from '@/lib/logger';
import { updateListItem, deleteListItem } from '@/utils/listUpdates';
import { toggleUserActive, deleteUserGDPR } from '@/lib/actions/settings-actions';
import { useTranslation } from '@/i18n/client';
import { LOCALE_MAP } from '@/i18n/settings';
import { SettingsSection } from '@/components/settings/SettingsSection';
import type { BaseSettingsProps } from '@/types/settings';

// Language code to display label (universal, not translated)
// Maps both frontend Language codes and backend codes (zh vs zh-CN)
const LANGUAGE_CODES: Record<string, string> = {
  fr: 'FR',
  en: 'EN',
  es: 'ES',
  de: 'DE',
  it: 'IT',
  zh: 'ZH',
  'zh-CN': 'ZH', // Backend uses zh-CN, but display same label
};

interface User {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_verified: boolean;
  is_superuser: boolean;
  created_at: string;
  // User preferences
  language: string;
  personality_id: string | null;
  voice_enabled: boolean;
  memory_enabled: boolean;
  tokens_display_enabled: boolean;
  // Statistics (from UserProfileWithStats) - Lifetime totals
  last_login: string | null;
  last_message_at: string | null;
  total_messages: number;
  total_tokens: number;
  tokens_in: number;
  tokens_out: number;
  tokens_cache: number;
  total_cost_eur: number;
  total_google_api_requests: number;
  // Statistics - Current billing cycle
  cycle_messages: number;
  cycle_tokens: number;
  cycle_google_api_requests: number;
  cycle_cost_eur: number;
  // Other stats
  active_connectors_count: number;
  memories_count: number;
  interests_count: number;
}

interface UserListResponse {
  users: User[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export default function AdminUsersSection({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng, 'translation');
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);

  // ✅ React 19 useOptimistic for instant UI updates without full page refresh
  const [optimisticUsers, updateOptimisticUsers] = useOptimistic(
    users,
    (
      state: User[],
      optimisticValue: { id: string; updates?: Partial<User>; deleted?: boolean }
    ) => {
      if (optimisticValue.deleted) {
        return deleteListItem(state, optimisticValue.id);
      }
      if (optimisticValue.updates) {
        return updateListItem(state, optimisticValue.id, optimisticValue.updates);
      }
      return state;
    }
  );

  // ✅ useTransition for pending state during mutations
  const [isPending, startTransition] = useTransition();

  // Pagination and sorting state
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [sortBy, setSortBy] = useState<'email' | 'full_name' | 'created_at' | 'is_active'>(
    'created_at'
  );
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  // Search state (managed by SearchInput)
  const [searchQuery, setSearchQuery] = useState('');

  // ✅ FIXED: Proper fetchUsers with AbortController to prevent race conditions
  const fetchUsers = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true);
      try {
        const params: Record<string, string | number> = {
          page,
          page_size: ADMIN_USERS_PAGE_SIZE,
          sort_by: sortBy,
          sort_order: sortOrder,
        };
        if (searchQuery) params.q = searchQuery;

        const response = await apiClient.get<UserListResponse>('/users/admin/search', {
          params,
          signal,
        });
        setUsers(response.users);
        setPage(response.page);
        setTotalPages(response.total_pages);
      } catch (error) {
        const err = error as { name?: string };
        // ✅ Don't show error if request was aborted (normal behavior)
        if (err.name === 'AbortError' || err.name === 'CanceledError') {
          return;
        }
        logger.error('Failed to fetch users', error as Error, {
          component: 'AdminUsersSection',
          endpoint: '/users/admin/search',
          page,
          sortBy,
          sortOrder,
        });
        toast.error(t('settings.admin.users.errors.loading'));
      } finally {
        setLoading(false);
      }
    },
    [page, sortBy, sortOrder, searchQuery, t]
  );

  // ✅ FIXED: useEffect with cleanup for AbortController
  useEffect(() => {
    const controller = new AbortController();
    fetchUsers(controller.signal);

    return () => {
      controller.abort();
    };
  }, [fetchUsers]);

  // ✅ REMOVED: Duplicate autoDismiss useEffect
  // Alert component now handles autoDismiss via autoDismiss={5000} prop

  const handleSearchChange = (value: string) => {
    setSearchQuery(value);
    setPage(1); // Reset to page 1 when searching
  };

  const handleSort = (column: typeof sortBy) => {
    if (sortBy === column) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(column);
      setSortOrder('asc');
    }
  };

  // ✅ React 19 useOptimistic pattern: instant UI update with automatic rollback on error
  const handleToggleActive = (userId: string, currentStatus: boolean) => {
    let reason: string | null = null;

    if (currentStatus) {
      // Deactivating - ask for reason
      reason = prompt(t('settings.admin.users.deactivation_reason_prompt'));
      if (!reason) return; // User cancelled
    }

    startTransition(async () => {
      // 1. Optimistic UI update (instant)
      updateOptimisticUsers({ id: userId, updates: { is_active: !currentStatus } });

      try {
        // 2. Server Action call
        const result = await toggleUserActive(userId, !currentStatus, reason);

        if (result.success) {
          // 3. Update confirmed state (React reconciles automatically)
          setUsers(prevUsers => updateListItem(prevUsers, userId, { is_active: !currentStatus }));
          toast.success(result.message!);
        } else {
          // 4. Rollback on error (React reverts optimistic update)
          toast.error(result.error!);
        }
      } catch {
        // 5. Rollback on exception (React reverts optimistic update)
        toast.error(
          t('settings.admin.users.errors.toggle_status', {
            action: currentStatus
              ? t('settings.admin.users.actions.deactivate').toLowerCase()
              : t('settings.admin.users.actions.activate').toLowerCase(),
          })
        );
      }
    });
  };

  // ✅ React 19 useOptimistic pattern: instant deletion with automatic rollback on error
  const handleDeleteUser = (userId: string, userEmail: string) => {
    const confirmed = confirm(t('settings.admin.users.delete_confirmation', { email: userEmail }));

    if (!confirmed) return;

    startTransition(async () => {
      // 1. Optimistic UI update (instant removal)
      updateOptimisticUsers({ id: userId, deleted: true });

      try {
        // 2. Server Action call
        const result = await deleteUserGDPR(userId);

        if (result.success) {
          // 3. Update confirmed state (React reconciles automatically)
          setUsers(prevUsers => deleteListItem(prevUsers, userId));
          toast.success(result.message!);
        } else {
          // 4. Rollback on error (React reverts optimistic update)
          toast.error(result.error!);
        }
      } catch {
        // 5. Rollback on exception (React reverts optimistic update)
        toast.error(t('settings.admin.users.errors.delete'));
      }
    });
  };

  // Loading state content
  if (loading && users.length === 0) {
    return (
      <SettingsSection
        value="admin-users"
        title={t('settings.admin.users.title')}
        description={t('settings.admin.users.description')}
        icon={Users}
        collapsible={collapsible}
      >
        <TableSkeleton rows={5} />
      </SettingsSection>
    );
  }

  // Main content
  const content = (
    <>
      {/* Search */}
      <div className="mb-4">
        <SearchInput
          placeholder={t('settings.admin.users.search_placeholder')}
          onSearchChange={handleSearchChange}
          debounceMs={SEARCH_DEBOUNCE_MS}
          loading={loading}
          aria-label={t('settings.admin.users.search_aria')}
        />
      </div>

      {/* Users Table */}
      {loading && users.length === 0 ? (
        <TableSkeleton rows={5} />
      ) : (
        <>
          <div
            className={`overflow-x-auto rounded-lg border border-border transition-opacity duration-150 ${loading ? 'opacity-60' : 'opacity-100'}`}
          >
            <table className="min-w-full divide-y divide-border" role="table">
              <thead className="bg-muted/50">
                <tr>
                  {/* ✅ ACCESSIBILITY: aria-sort for sortable columns */}
                  <th
                    className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider cursor-pointer hover:bg-muted transition-colors"
                    onClick={() => handleSort('email')}
                    aria-sort={
                      sortBy === 'email'
                        ? sortOrder === 'asc'
                          ? 'ascending'
                          : 'descending'
                        : 'none'
                    }
                    role="columnheader"
                  >
                    <div className="flex items-center space-x-1">
                      <span>{t('settings.admin.users.table.email')}</span>
                      {sortBy === 'email' && (
                        <span aria-hidden="true">{sortOrder === 'asc' ? '↑' : '↓'}</span>
                      )}
                    </div>
                  </th>
                  <th
                    className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider cursor-pointer hover:bg-muted transition-colors"
                    onClick={() => handleSort('full_name')}
                    aria-sort={
                      sortBy === 'full_name'
                        ? sortOrder === 'asc'
                          ? 'ascending'
                          : 'descending'
                        : 'none'
                    }
                    role="columnheader"
                  >
                    <div className="flex items-center space-x-1">
                      <span>{t('settings.admin.users.table.name')}</span>
                      {sortBy === 'full_name' && (
                        <span aria-hidden="true">{sortOrder === 'asc' ? '↑' : '↓'}</span>
                      )}
                    </div>
                  </th>
                  <th
                    className="px-3 py-3 text-center text-xs font-medium text-muted-foreground uppercase tracking-wider"
                    role="columnheader"
                    title={t('settings.admin.users.table.language')}
                  >
                    {t('settings.admin.users.table.lang_short')}
                  </th>
                  <th
                    className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider cursor-pointer hover:bg-muted transition-colors"
                    onClick={() => handleSort('is_active')}
                    aria-sort={
                      sortBy === 'is_active'
                        ? sortOrder === 'asc'
                          ? 'ascending'
                          : 'descending'
                        : 'none'
                    }
                    role="columnheader"
                  >
                    <div className="flex items-center space-x-1">
                      <span>{t('settings.admin.users.table.status')}</span>
                      {sortBy === 'is_active' && (
                        <span aria-hidden="true">{sortOrder === 'asc' ? '↑' : '↓'}</span>
                      )}
                    </div>
                  </th>
                  <th
                    className="px-3 py-3 text-center text-xs font-medium text-muted-foreground uppercase tracking-wider"
                    role="columnheader"
                    title={t('settings.admin.users.table.voice')}
                  >
                    <Volume2 className="h-4 w-4 mx-auto" />
                  </th>
                  <th
                    className="px-3 py-3 text-center text-xs font-medium text-muted-foreground uppercase tracking-wider"
                    role="columnheader"
                    title={t('settings.admin.users.table.memory')}
                  >
                    <Brain className="h-4 w-4 mx-auto" />
                  </th>
                  <th
                    className="px-3 py-3 text-center text-xs font-medium text-muted-foreground uppercase tracking-wider"
                    role="columnheader"
                    title={t('settings.admin.users.table.tokens_display')}
                  >
                    <Eye className="h-4 w-4 mx-auto" />
                  </th>
                  <th
                    className="px-3 py-3 text-center text-xs font-medium text-muted-foreground uppercase tracking-wider"
                    role="columnheader"
                    title={t('settings.admin.users.table.connectors')}
                  >
                    <Plug className="h-4 w-4 mx-auto" />
                  </th>
                  <th
                    className="px-3 py-3 text-center text-xs font-medium text-muted-foreground uppercase tracking-wider"
                    role="columnheader"
                    title={t('settings.admin.users.table.memories')}
                  >
                    <Bookmark className="h-4 w-4 mx-auto" />
                  </th>
                  <th
                    className="px-3 py-3 text-center text-xs font-medium text-muted-foreground uppercase tracking-wider"
                    role="columnheader"
                    title={t('settings.admin.users.table.interests')}
                  >
                    <Sparkles className="h-4 w-4 mx-auto" />
                  </th>
                  <th
                    className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider"
                    role="columnheader"
                  >
                    {t('settings.admin.users.table.actions')}
                  </th>
                  <th
                    className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider"
                    role="columnheader"
                  >
                    {t('settings.admin.users.table.last_message')}
                  </th>
                  <th
                    className="px-3 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider"
                    role="columnheader"
                  >
                    {t('settings.admin.users.table.messages_short')}
                  </th>
                  <th
                    className="px-3 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider"
                    role="columnheader"
                  >
                    {t('settings.admin.users.table.tokens')}
                  </th>
                  <th
                    className="px-3 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider"
                    role="columnheader"
                  >
                    {t('settings.admin.users.table.google_api')}
                  </th>
                  <th
                    className="px-3 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider"
                    role="columnheader"
                  >
                    {t('settings.admin.users.table.cost')}
                  </th>
                  <th
                    className="px-3 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider"
                    role="columnheader"
                  >
                    {t('settings.admin.users.table.msgs_period')}
                  </th>
                  <th
                    className="px-3 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider"
                    role="columnheader"
                  >
                    {t('settings.admin.users.table.tokens_period')}
                  </th>
                  <th
                    className="px-3 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider"
                    role="columnheader"
                  >
                    {t('settings.admin.users.table.google_api_period')}
                  </th>
                  <th
                    className="px-3 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider"
                    role="columnheader"
                  >
                    {t('settings.admin.users.table.cost_period')}
                  </th>
                </tr>
              </thead>
              <tbody className="bg-card divide-y divide-border">
                {optimisticUsers.map(user => (
                  <tr
                    key={user.id}
                    className={`transition-colors hover:bg-muted/30 ${isPending ? 'opacity-60' : ''}`}
                  >
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-foreground">
                      {user.email}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-foreground">
                      {user.full_name || '-'}
                    </td>
                    {/* Language */}
                    <td className="px-3 py-3 whitespace-nowrap text-sm text-center">
                      <span className="text-xs font-medium text-muted-foreground">
                        {LANGUAGE_CODES[user.language] || user.language}
                      </span>
                    </td>
                    {/* Status */}
                    <td className="px-4 py-3 whitespace-nowrap text-sm">
                      <span
                        className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${
                          user.is_active
                            ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200 border border-green-200 dark:border-green-800'
                            : 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200 border border-red-200 dark:border-red-800'
                        }`}
                      >
                        {user.is_active
                          ? t('settings.admin.users.status.active')
                          : t('settings.admin.users.status.inactive')}
                      </span>
                      {user.is_superuser && (
                        <span className="ml-1 text-primary font-semibold text-xs">★</span>
                      )}
                    </td>
                    {/* Voice enabled */}
                    <td className="px-3 py-3 whitespace-nowrap text-center">
                      {user.voice_enabled ? (
                        <Volume2 className="h-4 w-4 mx-auto text-green-600 dark:text-green-400" />
                      ) : (
                        <VolumeOff className="h-4 w-4 mx-auto text-muted-foreground/40" />
                      )}
                    </td>
                    {/* Memory enabled */}
                    <td className="px-3 py-3 whitespace-nowrap text-center">
                      {user.memory_enabled ? (
                        <Brain className="h-4 w-4 mx-auto text-green-600 dark:text-green-400" />
                      ) : (
                        <Brain className="h-4 w-4 mx-auto text-muted-foreground/40" />
                      )}
                    </td>
                    {/* Tokens display enabled */}
                    <td className="px-3 py-3 whitespace-nowrap text-center">
                      {user.tokens_display_enabled ? (
                        <Eye className="h-4 w-4 mx-auto text-green-600 dark:text-green-400" />
                      ) : (
                        <EyeOff className="h-4 w-4 mx-auto text-muted-foreground/40" />
                      )}
                    </td>
                    {/* Active connectors count */}
                    <td className="px-3 py-3 whitespace-nowrap text-center">
                      <span
                        className={`text-sm font-medium tabular-nums ${user.active_connectors_count > 0 ? 'text-green-600 dark:text-green-400' : 'text-muted-foreground/40'}`}
                      >
                        {user.active_connectors_count}
                      </span>
                    </td>
                    {/* Memories count */}
                    <td className="px-3 py-3 whitespace-nowrap text-center">
                      <span
                        className={`text-sm font-medium tabular-nums ${user.memories_count > 0 ? 'text-primary' : 'text-muted-foreground/40'}`}
                      >
                        {user.memories_count}
                      </span>
                    </td>
                    {/* Interests count */}
                    <td className="px-3 py-3 whitespace-nowrap text-center">
                      <span
                        className={`text-sm font-medium tabular-nums ${user.interests_count > 0 ? 'text-primary' : 'text-muted-foreground/40'}`}
                      >
                        {user.interests_count}
                      </span>
                    </td>
                    {/* Actions */}
                    <td className="px-4 py-3 whitespace-nowrap text-sm">
                      <div className="flex gap-2">
                        <Button
                          variant={user.is_active ? 'destructive' : 'success'}
                          size="sm"
                          onClick={() => handleToggleActive(user.id, user.is_active)}
                          disabled={isPending}
                          className="min-w-[80px] justify-center"
                          aria-label={`${user.is_active ? t('settings.admin.users.actions.deactivate') : t('settings.admin.users.actions.activate')} ${user.email}`}
                        >
                          {user.is_active
                            ? t('settings.admin.users.actions.deactivate')
                            : t('settings.admin.users.actions.activate')}
                        </Button>
                        {!user.is_superuser && (
                          <Button
                            variant="destructive"
                            size="sm"
                            onClick={() => handleDeleteUser(user.id, user.email)}
                            disabled={isPending}
                            className="min-w-[80px] justify-center"
                            aria-label={`${t('settings.admin.users.actions.delete')} ${user.email}`}
                          >
                            {t('settings.admin.users.actions.delete')}
                          </Button>
                        )}
                      </div>
                    </td>
                    {/* Last message at */}
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-muted-foreground">
                      {user.last_message_at ? (
                        <span
                          title={new Date(user.last_message_at).toLocaleString(LOCALE_MAP[lng])}
                        >
                          {new Date(user.last_message_at).toLocaleDateString(LOCALE_MAP[lng], {
                            day: '2-digit',
                            month: '2-digit',
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </span>
                      ) : (
                        <span className="text-muted-foreground/40">-</span>
                      )}
                    </td>
                    {/* Messages count */}
                    <td className="px-3 py-3 whitespace-nowrap text-sm text-right tabular-nums">
                      {user.total_messages.toLocaleString(LOCALE_MAP[lng])}
                    </td>
                    {/* Total tokens */}
                    <td className="px-3 py-3 whitespace-nowrap text-sm text-right tabular-nums font-medium">
                      {user.total_tokens.toLocaleString(LOCALE_MAP[lng])}
                    </td>
                    {/* Total Google API requests */}
                    <td className="px-3 py-3 whitespace-nowrap text-sm text-right tabular-nums">
                      {user.total_google_api_requests.toLocaleString(LOCALE_MAP[lng])}
                    </td>
                    {/* Total cost */}
                    <td className="px-3 py-3 whitespace-nowrap text-sm text-right tabular-nums font-bold">
                      {user.total_cost_eur.toLocaleString(LOCALE_MAP[lng], {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                      €
                    </td>
                    {/* Cycle messages */}
                    <td className="px-3 py-3 whitespace-nowrap text-sm text-right tabular-nums text-muted-foreground">
                      {user.cycle_messages.toLocaleString(LOCALE_MAP[lng])}
                    </td>
                    {/* Cycle tokens */}
                    <td className="px-3 py-3 whitespace-nowrap text-sm text-right tabular-nums text-muted-foreground">
                      {user.cycle_tokens.toLocaleString(LOCALE_MAP[lng])}
                    </td>
                    {/* Cycle Google API requests */}
                    <td className="px-3 py-3 whitespace-nowrap text-sm text-right tabular-nums text-muted-foreground">
                      {user.cycle_google_api_requests.toLocaleString(LOCALE_MAP[lng])}
                    </td>
                    {/* Cycle cost */}
                    <td className="px-3 py-3 whitespace-nowrap text-sm text-right tabular-nums font-bold text-muted-foreground">
                      {user.cycle_cost_eur.toLocaleString(LOCALE_MAP[lng], {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                      €
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <Pagination
            currentPage={page}
            totalPages={totalPages}
            onPageChange={setPage}
            variant="centered"
            className="mt-4"
          />
        </>
      )}
    </>
  );

  return (
    <SettingsSection
      value="admin-users"
      title={t('settings.admin.users.title')}
      description={t('settings.admin.users.description')}
      icon={Users}
      collapsible={collapsible}
    >
      {content}
    </SettingsSection>
  );
}
