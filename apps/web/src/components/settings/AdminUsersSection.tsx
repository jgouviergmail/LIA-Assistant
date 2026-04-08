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
  Blocks,
  Server,
  Clock,
  Database,
  ShieldOff,
} from 'lucide-react';
import apiClient from '@/lib/api-client';
import { ADMIN_USERS_PAGE_SIZE, SEARCH_DEBOUNCE_MS } from '@/lib/constants';
import { logger } from '@/lib/logger';
import { updateListItem, deleteListItem } from '@/utils/listUpdates';
import {
  toggleUserActive,
  deleteUserAccount,
  deleteUserGDPR,
} from '@/lib/actions/settings-actions';
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
  skills_count: number;
  mcp_servers_count: number;
  scheduled_actions_count: number;
  rag_spaces_count: number;
  is_usage_blocked: boolean;
  deleted_at: string | null;
  is_deleted: boolean;
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
  const [pageSize, setPageSize] = useState(ADMIN_USERS_PAGE_SIZE);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  // All sortable columns — must match backend sort_by options
  type SortableColumn =
    | 'email'
    | 'full_name'
    | 'created_at'
    | 'is_active'
    | 'language'
    | 'voice_enabled'
    | 'memory_enabled'
    | 'tokens_display_enabled'
    | 'is_usage_blocked'
    | 'active_connectors_count'
    | 'memories_count'
    | 'interests_count'
    | 'skills_count'
    | 'mcp_servers_count'
    | 'scheduled_actions_count'
    | 'rag_spaces_count'
    | 'last_message_at'
    | 'total_messages'
    | 'total_tokens'
    | 'total_google_api_requests'
    | 'total_cost_eur'
    | 'cycle_messages'
    | 'cycle_tokens'
    | 'cycle_google_api_requests'
    | 'cycle_cost_eur';
  const [sortBy, setSortBy] = useState<SortableColumn>('created_at');
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
          page_size: pageSize,
          sort_by: sortBy,
          sort_order: sortOrder,
        };
        if (searchQuery) params.q = searchQuery;

        const response = await apiClient.get<UserListResponse>('/users/admin/search', {
          params,
          signal,
        });
        setUsers(response.users);
        setTotal(response.total);
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
    [page, pageSize, sortBy, sortOrder, searchQuery, t]
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

  const handleSort = (column: SortableColumn) => {
    if (sortBy === column) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(column);
      setSortOrder('asc');
    }
    setPage(1);
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

  // ✅ Soft-delete: purge personal data, preserve billing history
  // Precondition: user must be deactivated (is_active=false)
  const handleDeleteUser = (userId: string, userEmail: string) => {
    const confirmed = confirm(t('settings.admin.users.delete_confirmation', { email: userEmail }));

    if (!confirmed) return;

    startTransition(async () => {
      try {
        const result = await deleteUserAccount(userId);

        if (result.success) {
          // Refresh list to show updated deleted_at status
          setUsers(prevUsers =>
            prevUsers.map(u =>
              u.id === userId ? { ...u, is_deleted: true, deleted_at: new Date().toISOString() } : u
            )
          );
          toast.success(result.message!);
        } else {
          toast.error(result.error!);
        }
      } catch {
        toast.error(t('settings.admin.users.errors.delete'));
      }
    });
  };

  // ✅ GDPR hard-erase: permanently remove user row (email, name) from database
  // Precondition: user must be soft-deleted (is_deleted=true)
  const handleEraseUser = (userId: string, userEmail: string) => {
    const confirmed = confirm(t('settings.admin.users.erase_confirmation', { email: userEmail }));

    if (!confirmed) return;

    startTransition(async () => {
      // 1. Optimistic UI update (instant removal)
      updateOptimisticUsers({ id: userId, deleted: true });

      try {
        const result = await deleteUserGDPR(userId);

        if (result.success) {
          setUsers(prevUsers => deleteListItem(prevUsers, userId));
          toast.success(result.message!);
        } else {
          toast.error(result.error!);
        }
      } catch {
        toast.error(t('settings.admin.users.errors.erase'));
      }
    });
  };

  // Sort indicator arrow
  const sortArrow = (column: SortableColumn) =>
    sortBy === column ? (sortOrder === 'asc' ? '↑' : '↓') : null;

  // aria-sort value for a column
  const ariaSort = (column: SortableColumn): 'ascending' | 'descending' | 'none' =>
    sortBy === column ? (sortOrder === 'asc' ? 'ascending' : 'descending') : 'none';

  // Common classes for sortable text headers
  const sortableTextCls =
    'px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider cursor-pointer hover:bg-muted transition-colors';

  // Common classes for sortable icon headers (center-aligned)
  const sortableIconCls =
    'px-3 py-3 text-center text-xs font-medium text-muted-foreground uppercase tracking-wider cursor-pointer hover:bg-muted transition-colors';

  // Common classes for sortable right-aligned headers (stats)
  const sortableRightCls =
    'px-3 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider cursor-pointer hover:bg-muted transition-colors';

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
                  {/* Email */}
                  <th
                    className={sortableTextCls}
                    onClick={() => handleSort('email')}
                    aria-sort={ariaSort('email')}
                    role="columnheader"
                  >
                    <div className="flex items-center space-x-1">
                      <span>{t('settings.admin.users.table.email')}</span>
                      {sortArrow('email') && <span aria-hidden="true">{sortArrow('email')}</span>}
                    </div>
                  </th>
                  {/* Name */}
                  <th
                    className={sortableTextCls}
                    onClick={() => handleSort('full_name')}
                    aria-sort={ariaSort('full_name')}
                    role="columnheader"
                  >
                    <div className="flex items-center space-x-1">
                      <span>{t('settings.admin.users.table.name')}</span>
                      {sortArrow('full_name') && (
                        <span aria-hidden="true">{sortArrow('full_name')}</span>
                      )}
                    </div>
                  </th>
                  {/* Language */}
                  <th
                    className={sortableIconCls}
                    onClick={() => handleSort('language')}
                    aria-sort={ariaSort('language')}
                    role="columnheader"
                    title={t('settings.admin.users.table.language')}
                  >
                    <span className="inline-flex items-center gap-0.5">
                      {t('settings.admin.users.table.lang_short')}
                      {sortArrow('language') && (
                        <span aria-hidden="true">{sortArrow('language')}</span>
                      )}
                    </span>
                  </th>
                  {/* Status */}
                  <th
                    className={sortableTextCls}
                    onClick={() => handleSort('is_active')}
                    aria-sort={ariaSort('is_active')}
                    role="columnheader"
                  >
                    <div className="flex items-center space-x-1">
                      <span>{t('settings.admin.users.table.status')}</span>
                      {sortArrow('is_active') && (
                        <span aria-hidden="true">{sortArrow('is_active')}</span>
                      )}
                    </div>
                  </th>
                  {/* Usage blocked */}
                  <th
                    className={sortableIconCls}
                    onClick={() => handleSort('is_usage_blocked')}
                    aria-sort={ariaSort('is_usage_blocked')}
                    role="columnheader"
                    title={t('settings.admin.users.table.blocked')}
                  >
                    <span className="inline-flex items-center gap-0.5 justify-center">
                      <ShieldOff className="h-4 w-4" />
                      {sortArrow('is_usage_blocked') && (
                        <span aria-hidden="true">{sortArrow('is_usage_blocked')}</span>
                      )}
                    </span>
                  </th>
                  {/* Voice */}
                  <th
                    className={sortableIconCls}
                    onClick={() => handleSort('voice_enabled')}
                    aria-sort={ariaSort('voice_enabled')}
                    role="columnheader"
                    title={t('settings.admin.users.table.voice')}
                  >
                    <span className="inline-flex items-center gap-0.5 justify-center">
                      <Volume2 className="h-4 w-4" />
                      {sortArrow('voice_enabled') && (
                        <span aria-hidden="true">{sortArrow('voice_enabled')}</span>
                      )}
                    </span>
                  </th>
                  {/* Memory */}
                  <th
                    className={sortableIconCls}
                    onClick={() => handleSort('memory_enabled')}
                    aria-sort={ariaSort('memory_enabled')}
                    role="columnheader"
                    title={t('settings.admin.users.table.memory')}
                  >
                    <span className="inline-flex items-center gap-0.5 justify-center">
                      <Brain className="h-4 w-4" />
                      {sortArrow('memory_enabled') && (
                        <span aria-hidden="true">{sortArrow('memory_enabled')}</span>
                      )}
                    </span>
                  </th>
                  {/* Tokens display */}
                  <th
                    className={sortableIconCls}
                    onClick={() => handleSort('tokens_display_enabled')}
                    aria-sort={ariaSort('tokens_display_enabled')}
                    role="columnheader"
                    title={t('settings.admin.users.table.tokens_display')}
                  >
                    <span className="inline-flex items-center gap-0.5 justify-center">
                      <Eye className="h-4 w-4" />
                      {sortArrow('tokens_display_enabled') && (
                        <span aria-hidden="true">{sortArrow('tokens_display_enabled')}</span>
                      )}
                    </span>
                  </th>
                  {/* Connectors count */}
                  <th
                    className={sortableIconCls}
                    onClick={() => handleSort('active_connectors_count')}
                    aria-sort={ariaSort('active_connectors_count')}
                    role="columnheader"
                    title={t('settings.admin.users.table.connectors')}
                  >
                    <span className="inline-flex items-center gap-0.5 justify-center">
                      <Plug className="h-4 w-4" />
                      {sortArrow('active_connectors_count') && (
                        <span aria-hidden="true">{sortArrow('active_connectors_count')}</span>
                      )}
                    </span>
                  </th>
                  {/* Memories count */}
                  <th
                    className={sortableIconCls}
                    onClick={() => handleSort('memories_count')}
                    aria-sort={ariaSort('memories_count')}
                    role="columnheader"
                    title={t('settings.admin.users.table.memories')}
                  >
                    <span className="inline-flex items-center gap-0.5 justify-center">
                      <Bookmark className="h-4 w-4" />
                      {sortArrow('memories_count') && (
                        <span aria-hidden="true">{sortArrow('memories_count')}</span>
                      )}
                    </span>
                  </th>
                  {/* Interests count */}
                  <th
                    className={sortableIconCls}
                    onClick={() => handleSort('interests_count')}
                    aria-sort={ariaSort('interests_count')}
                    role="columnheader"
                    title={t('settings.admin.users.table.interests')}
                  >
                    <span className="inline-flex items-center gap-0.5 justify-center">
                      <Sparkles className="h-4 w-4" />
                      {sortArrow('interests_count') && (
                        <span aria-hidden="true">{sortArrow('interests_count')}</span>
                      )}
                    </span>
                  </th>
                  {/* Skills count */}
                  <th
                    className={sortableIconCls}
                    onClick={() => handleSort('skills_count')}
                    aria-sort={ariaSort('skills_count')}
                    role="columnheader"
                    title={t('settings.admin.users.table.skills')}
                  >
                    <span className="inline-flex items-center gap-0.5 justify-center">
                      <Blocks className="h-4 w-4" />
                      {sortArrow('skills_count') && (
                        <span aria-hidden="true">{sortArrow('skills_count')}</span>
                      )}
                    </span>
                  </th>
                  {/* MCP servers count */}
                  <th
                    className={sortableIconCls}
                    onClick={() => handleSort('mcp_servers_count')}
                    aria-sort={ariaSort('mcp_servers_count')}
                    role="columnheader"
                    title={t('settings.admin.users.table.mcp_servers')}
                  >
                    <span className="inline-flex items-center gap-0.5 justify-center">
                      <Server className="h-4 w-4" />
                      {sortArrow('mcp_servers_count') && (
                        <span aria-hidden="true">{sortArrow('mcp_servers_count')}</span>
                      )}
                    </span>
                  </th>
                  {/* Scheduled actions count */}
                  <th
                    className={sortableIconCls}
                    onClick={() => handleSort('scheduled_actions_count')}
                    aria-sort={ariaSort('scheduled_actions_count')}
                    role="columnheader"
                    title={t('settings.admin.users.table.scheduled_actions')}
                  >
                    <span className="inline-flex items-center gap-0.5 justify-center">
                      <Clock className="h-4 w-4" />
                      {sortArrow('scheduled_actions_count') && (
                        <span aria-hidden="true">{sortArrow('scheduled_actions_count')}</span>
                      )}
                    </span>
                  </th>
                  {/* RAG spaces count */}
                  <th
                    className={sortableIconCls}
                    onClick={() => handleSort('rag_spaces_count')}
                    aria-sort={ariaSort('rag_spaces_count')}
                    role="columnheader"
                    title={t('settings.admin.users.table.rag_spaces')}
                  >
                    <span className="inline-flex items-center gap-0.5 justify-center">
                      <Database className="h-4 w-4" />
                      {sortArrow('rag_spaces_count') && (
                        <span aria-hidden="true">{sortArrow('rag_spaces_count')}</span>
                      )}
                    </span>
                  </th>
                  {/* Actions — not sortable */}
                  <th
                    className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider"
                    role="columnheader"
                  >
                    {t('settings.admin.users.table.actions')}
                  </th>
                  {/* Last message */}
                  <th
                    className={sortableTextCls}
                    onClick={() => handleSort('last_message_at')}
                    aria-sort={ariaSort('last_message_at')}
                    role="columnheader"
                  >
                    <div className="flex items-center space-x-1">
                      <span>{t('settings.admin.users.table.last_message')}</span>
                      {sortArrow('last_message_at') && (
                        <span aria-hidden="true">{sortArrow('last_message_at')}</span>
                      )}
                    </div>
                  </th>
                  {/* Lifetime stats */}
                  <th
                    className={sortableRightCls}
                    onClick={() => handleSort('total_messages')}
                    aria-sort={ariaSort('total_messages')}
                    role="columnheader"
                  >
                    <span className="inline-flex items-center gap-0.5 justify-end">
                      {t('settings.admin.users.table.messages_short')}
                      {sortArrow('total_messages') && (
                        <span aria-hidden="true">{sortArrow('total_messages')}</span>
                      )}
                    </span>
                  </th>
                  <th
                    className={sortableRightCls}
                    onClick={() => handleSort('total_tokens')}
                    aria-sort={ariaSort('total_tokens')}
                    role="columnheader"
                  >
                    <span className="inline-flex items-center gap-0.5 justify-end">
                      {t('settings.admin.users.table.tokens')}
                      {sortArrow('total_tokens') && (
                        <span aria-hidden="true">{sortArrow('total_tokens')}</span>
                      )}
                    </span>
                  </th>
                  <th
                    className={sortableRightCls}
                    onClick={() => handleSort('total_google_api_requests')}
                    aria-sort={ariaSort('total_google_api_requests')}
                    role="columnheader"
                  >
                    <span className="inline-flex items-center gap-0.5 justify-end">
                      {t('settings.admin.users.table.google_api')}
                      {sortArrow('total_google_api_requests') && (
                        <span aria-hidden="true">{sortArrow('total_google_api_requests')}</span>
                      )}
                    </span>
                  </th>
                  <th
                    className={sortableRightCls}
                    onClick={() => handleSort('total_cost_eur')}
                    aria-sort={ariaSort('total_cost_eur')}
                    role="columnheader"
                  >
                    <span className="inline-flex items-center gap-0.5 justify-end">
                      {t('settings.admin.users.table.cost')}
                      {sortArrow('total_cost_eur') && (
                        <span aria-hidden="true">{sortArrow('total_cost_eur')}</span>
                      )}
                    </span>
                  </th>
                  {/* Cycle stats */}
                  <th
                    className={sortableRightCls}
                    onClick={() => handleSort('cycle_messages')}
                    aria-sort={ariaSort('cycle_messages')}
                    role="columnheader"
                  >
                    <span className="inline-flex items-center gap-0.5 justify-end">
                      {t('settings.admin.users.table.msgs_period')}
                      {sortArrow('cycle_messages') && (
                        <span aria-hidden="true">{sortArrow('cycle_messages')}</span>
                      )}
                    </span>
                  </th>
                  <th
                    className={sortableRightCls}
                    onClick={() => handleSort('cycle_tokens')}
                    aria-sort={ariaSort('cycle_tokens')}
                    role="columnheader"
                  >
                    <span className="inline-flex items-center gap-0.5 justify-end">
                      {t('settings.admin.users.table.tokens_period')}
                      {sortArrow('cycle_tokens') && (
                        <span aria-hidden="true">{sortArrow('cycle_tokens')}</span>
                      )}
                    </span>
                  </th>
                  <th
                    className={sortableRightCls}
                    onClick={() => handleSort('cycle_google_api_requests')}
                    aria-sort={ariaSort('cycle_google_api_requests')}
                    role="columnheader"
                  >
                    <span className="inline-flex items-center gap-0.5 justify-end">
                      {t('settings.admin.users.table.google_api_period')}
                      {sortArrow('cycle_google_api_requests') && (
                        <span aria-hidden="true">{sortArrow('cycle_google_api_requests')}</span>
                      )}
                    </span>
                  </th>
                  <th
                    className={sortableRightCls}
                    onClick={() => handleSort('cycle_cost_eur')}
                    aria-sort={ariaSort('cycle_cost_eur')}
                    role="columnheader"
                  >
                    <span className="inline-flex items-center gap-0.5 justify-end">
                      {t('settings.admin.users.table.cost_period')}
                      {sortArrow('cycle_cost_eur') && (
                        <span aria-hidden="true">{sortArrow('cycle_cost_eur')}</span>
                      )}
                    </span>
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
                          user.is_deleted
                            ? 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400 border border-gray-300 dark:border-gray-600 line-through'
                            : user.is_active
                              ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200 border border-green-200 dark:border-green-800'
                              : 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200 border border-red-200 dark:border-red-800'
                        }`}
                      >
                        {user.is_deleted
                          ? t('settings.admin.users.status.deleted')
                          : user.is_active
                            ? t('settings.admin.users.status.active')
                            : t('settings.admin.users.status.inactive')}
                      </span>
                      {user.is_superuser && (
                        <span className="ml-1 text-primary font-semibold text-xs">★</span>
                      )}
                    </td>
                    {/* Usage blocked */}
                    <td className="px-3 py-3 whitespace-nowrap text-center">
                      {user.is_usage_blocked ? (
                        <ShieldOff className="h-4 w-4 mx-auto text-destructive" />
                      ) : (
                        <span className="text-muted-foreground/40">—</span>
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
                    {/* Skills count */}
                    <td className="px-3 py-3 whitespace-nowrap text-center">
                      <span
                        className={`text-sm font-medium tabular-nums ${user.skills_count > 0 ? 'text-primary' : 'text-muted-foreground/40'}`}
                      >
                        {user.skills_count}
                      </span>
                    </td>
                    {/* MCP servers count */}
                    <td className="px-3 py-3 whitespace-nowrap text-center">
                      <span
                        className={`text-sm font-medium tabular-nums ${user.mcp_servers_count > 0 ? 'text-primary' : 'text-muted-foreground/40'}`}
                      >
                        {user.mcp_servers_count}
                      </span>
                    </td>
                    {/* Scheduled actions count */}
                    <td className="px-3 py-3 whitespace-nowrap text-center">
                      <span
                        className={`text-sm font-medium tabular-nums ${user.scheduled_actions_count > 0 ? 'text-primary' : 'text-muted-foreground/40'}`}
                      >
                        {user.scheduled_actions_count}
                      </span>
                    </td>
                    {/* RAG spaces count */}
                    <td className="px-3 py-3 whitespace-nowrap text-center">
                      <span
                        className={`text-sm font-medium tabular-nums ${user.rag_spaces_count > 0 ? 'text-primary' : 'text-muted-foreground/40'}`}
                      >
                        {user.rag_spaces_count}
                      </span>
                    </td>
                    {/* Actions */}
                    <td className="px-4 py-3 whitespace-nowrap text-sm">
                      <div className="flex gap-2">
                        {/* Activate/Deactivate: hidden for deleted users (data purged, irreversible) */}
                        {!user.is_deleted && (
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
                        )}
                        {/* Delete: only for deactivated, non-deleted, non-superuser */}
                        {!user.is_superuser && !user.is_active && !user.is_deleted && (
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
                        {/* Erase (GDPR): only for already soft-deleted users */}
                        {!user.is_superuser && user.is_deleted && (
                          <Button
                            variant="destructive"
                            size="sm"
                            onClick={() => handleEraseUser(user.id, user.email)}
                            disabled={isPending}
                            className="min-w-[80px] justify-center"
                            aria-label={`${t('settings.admin.users.actions.erase')} ${user.email}`}
                          >
                            {t('settings.admin.users.actions.erase')}
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
            pageSize={pageSize}
            onPageSizeChange={setPageSize}
            totalItems={total}
            loading={loading}
            variant="justified"
            labels={{
              previous: t('common.previous'),
              next: t('common.next'),
              pageInfo: (current, pages) =>
                t('settings.admin.users.page_info', { page: current, totalPages: pages, total }),
              itemsPerPage: t('common.pagination.items_per_page'),
              totalItems: count => t('common.pagination.total_items', { count }),
            }}
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
