'use client';

import {
  useState,
  useEffect,
  useCallback,
  useOptimistic,
  useTransition,
  type ReactNode,
} from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { SearchInput } from '@/components/ui/search-input';
import { Pagination } from '@/components/ui/pagination';
import { TableSkeleton } from '@/components/ui/skeleton';
import { ShieldOff, Users, type LucideIcon } from 'lucide-react';
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
import { useConfirm } from '@/components/ui/use-confirm';
import { LOCALE_MAP, type Language } from '@/i18n/settings';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { BaseSettingsProps } from '@/types/settings';
import {
  ADMIN_USER_COUNT_COLUMNS,
  ADMIN_USER_STAT_COLUMNS,
  ADMIN_USER_SWITCHES,
  ADMIN_USER_SWITCH_ICONS,
  switchLabelKey,
  tableLabelKey,
  type AdminUserCount,
  type AdminUserStat,
  type AdminUserSwitch,
} from '@/components/settings/admin-users/columns';
import { ColumnLegend } from '@/components/settings/admin-users/ColumnLegend';
import { SortableHeader, type SortOrder } from '@/components/settings/admin-users/SortableHeader';

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

/**
 * A user row as returned by `/users/admin/search`. Exported so tests can build
 * a complete, contract-conformant fixture instead of duplicating the shape.
 *
 * Named `AdminUserRow`, not `User`: `@/lib/auth` already exports a `User` (the
 * authenticated session's own account, a different shape). Two exported `User`
 * types in one app is an import waiting to go to the wrong one.
 *
 * The switches (`voice_enabled`, `heartbeat_enabled`…) come from the declared
 * list: a switch the table renders is a field the row must carry.
 */
export interface AdminUserRow extends Record<AdminUserSwitch, boolean> {
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

/**
 * The lifecycle pill for one row.
 *
 * Extracted rather than inlined: the table's render function already sits at
 * the top of the CC ratchet, and three branches of status are three branches it
 * does not need to carry. It also replaces three hand-rolled
 * `{colour}-100/{colour}-900` pairs — the exact fixed palette `badge.tsx`
 * removed for ignoring the five colour themes and sitting outside the contrast
 * guard. `secondary` for a deleted account follows the doctrine that grey is
 * reserved for inactive states.
 */
function UserStatusBadge({ user, t }: { user: AdminUserRow; t: (key: string) => string }) {
  if (user.is_deleted) {
    return (
      <Badge variant="secondary" size="sm" className="line-through">
        {t('settings.admin.users.status.deleted')}
      </Badge>
    );
  }
  return (
    <Badge variant={user.is_active ? 'success' : 'destructive'} size="sm">
      {t(`settings.admin.users.status.${user.is_active ? 'active' : 'inactive'}`)}
    </Badge>
  );
}

/** Every column the listing sorts by — the backend's `ADMIN_USER_SORT_KEYS`. */
type SortableColumn =
  | 'email'
  | 'full_name'
  | 'created_at'
  | 'is_active'
  | 'language'
  | 'is_usage_blocked'
  | 'last_message_at'
  | AdminUserCount
  | AdminUserStat
  | AdminUserSwitch;

/**
 * The frozen columns: the email always, the name from the product's mobile
 * boundary (880 px) up — below it, two frozen columns would leave the phone
 * almost nothing to scroll. The name's offset is the email column's width
 * (`--admin-email-w`, set on the table) plus its horizontal padding. A frozen
 * cell is opaque, or the columns scrolling under it would show through, and
 * its hover tint is the row's own (`muted` at 30 % over `card`).
 */
const EMAIL_FROZEN =
  'sticky left-0 z-[1] shadow-[inset_-1px_0_0_var(--color-border)] mobile:shadow-none';
const NAME_FROZEN =
  'mobile:sticky mobile:left-[calc(var(--admin-email-w)+2rem)] mobile:z-[1] mobile:shadow-[inset_-1px_0_0_var(--color-border)]';
const FROZEN_BODY_BG =
  'bg-card group-hover:bg-[color-mix(in_srgb,var(--color-muted)_30%,var(--color-card))]';

interface UserListResponse {
  users: AdminUserRow[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export default function AdminUsersSection({ lng }: BaseSettingsProps) {
  const { t } = useTranslation(lng, 'translation');
  const [users, setUsers] = useState<AdminUserRow[]>([]);
  const [loading, setLoading] = useState(true);

  // ✅ React 19 useOptimistic for instant UI updates without full page refresh
  const [optimisticUsers, updateOptimisticUsers] = useOptimistic(
    users,
    (
      state: AdminUserRow[],
      optimisticValue: { id: string; updates?: Partial<AdminUserRow>; deleted?: boolean }
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
  // W4b: replaces two native `confirm()` on the account deletion / GDPR
  // erasure paths — an OS dialog whose buttons ignore the app's language.
  const { confirm, confirmDialog } = useConfirm();

  // Pagination and sorting state
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(ADMIN_USERS_PAGE_SIZE);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [sortBy, setSortBy] = useState<SortableColumn>('created_at');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');

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
  const handleDeleteUser = async (userId: string, userEmail: string) => {
    const confirmed = await confirm({
      title: t('settings.admin.users.delete_title'),
      description: t('settings.admin.users.delete_confirmation', { email: userEmail }),
      confirmLabel: t('settings.admin.users.actions.delete'),
    });

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
  const handleEraseUser = async (userId: string, userEmail: string) => {
    const confirmed = await confirm({
      title: t('settings.admin.users.erase_title'),
      description: t('settings.admin.users.erase_confirmation', { email: userEmail }),
      confirmLabel: t('settings.admin.users.actions.erase'),
    });

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

  const sortProps = { sortBy, sortOrder, onSort: handleSort };

  // Loading state content
  if (loading && users.length === 0) {
    return (
      <SettingsSection
        value="admin-users"
        title={t('settings.admin.users.title')}
        description={t('settings.admin.users.description')}
        icon={Users}
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
          <ColumnLegend t={t} />
          {/* A mutation dims the whole table (every row shares `isPending`),
              which also keeps the frozen cells opaque. */}
          <div
            className={cn(
              // `relative`: the `sr-only` labels are absolutely positioned, and
              // without a positioned scroller their containing block is the
              // page — they escape its clipping and widen the document.
              'relative overflow-x-auto rounded-lg border border-border transition-opacity duration-150',
              loading || isPending ? 'opacity-60' : 'opacity-100'
            )}
            aria-busy={loading || isPending}
          >
            <table className="min-w-full divide-y divide-border [--admin-email-w:9rem] [--admin-name-w:10rem] mobile:[--admin-email-w:14rem]">
              <thead className="bg-muted">
                <tr>
                  <SortableHeader
                    column="email"
                    label={t(tableLabelKey('email'))}
                    className={cn(EMAIL_FROZEN, 'bg-muted')}
                    {...sortProps}
                  />
                  <SortableHeader
                    column="full_name"
                    label={t(tableLabelKey('name'))}
                    className={cn(NAME_FROZEN, 'bg-muted')}
                    {...sortProps}
                  />
                  <SortableHeader
                    column="created_at"
                    label={t(tableLabelKey('registered'))}
                    {...sortProps}
                  />
                  <SortableHeader
                    column="language"
                    label={t(tableLabelKey('lang_short'))}
                    title={t(tableLabelKey('language'))}
                    align="center"
                    {...sortProps}
                  />
                  <SortableHeader
                    column="is_active"
                    label={t(tableLabelKey('status'))}
                    {...sortProps}
                  />
                  <SortableHeader
                    column="is_usage_blocked"
                    label={t(tableLabelKey('blocked'))}
                    icon={ShieldOff}
                    align="center"
                    {...sortProps}
                  />
                  {ADMIN_USER_COUNT_COLUMNS.map(column => (
                    <SortableHeader
                      key={column.key}
                      column={column.key}
                      label={t(tableLabelKey(column.labelKey))}
                      icon={column.icon}
                      align="center"
                      {...sortProps}
                    />
                  ))}
                  <th
                    scope="col"
                    className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground"
                  >
                    {t(tableLabelKey('actions'))}
                  </th>
                  <SortableHeader
                    column="last_message_at"
                    label={t(tableLabelKey('last_message'))}
                    {...sortProps}
                  />
                  {ADMIN_USER_STAT_COLUMNS.map(column => (
                    <SortableHeader
                      key={column.key}
                      column={column.key}
                      label={t(tableLabelKey(column.labelKey))}
                      align="right"
                      {...sortProps}
                    />
                  ))}
                  {ADMIN_USER_SWITCHES.map(key => (
                    <SortableHeader
                      key={key}
                      column={key}
                      label={t(switchLabelKey(key))}
                      icon={ADMIN_USER_SWITCH_ICONS[key]}
                      align="center"
                      {...sortProps}
                    />
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border bg-card">
                {optimisticUsers.map(user => (
                  <UserRow
                    key={user.id}
                    user={user}
                    lng={lng}
                    t={t}
                    actions={
                      <UserActions
                        user={user}
                        t={t}
                        disabled={isPending}
                        onToggleActive={handleToggleActive}
                        onDelete={handleDeleteUser}
                        onErase={handleEraseUser}
                      />
                    }
                  />
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
    >
      {content}
      {confirmDialog}
    </SettingsSection>
  );
}

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** A yes/no cell: the glyph when set, a dash when not, and the state spelled out for a screen reader. */
function FlagCell({
  on,
  icon: Icon,
  tone,
  t,
}: {
  on: boolean;
  icon: LucideIcon;
  tone: string;
  t: Translate;
}) {
  return (
    <td className="whitespace-nowrap px-3 py-3 text-center">
      {on ? (
        <Icon className={cn('mx-auto h-4 w-4', tone)} aria-hidden="true" />
      ) : (
        <span className="text-muted-foreground" aria-hidden="true">
          —
        </span>
      )}
      <span className="sr-only">
        {t(on ? 'settings.admin.users.state_on' : 'settings.admin.users.state_off')}
      </span>
    </td>
  );
}

const STAT_WEIGHT = {
  normal: '',
  medium: 'font-medium',
  bold: 'font-bold',
  cycle: 'text-muted-foreground',
  'cycle-bold': 'font-bold text-muted-foreground',
} as const;

function formatStat(value: number, kind: 'count' | 'eur', locale: string): string {
  if (kind === 'count') return value.toLocaleString(locale);
  return `${value.toLocaleString(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}€`;
}

/** Activate / deactivate, then delete, then the GDPR erase — each only where it applies. */
function UserActions({
  user,
  t,
  disabled,
  onToggleActive,
  onDelete,
  onErase,
}: {
  user: AdminUserRow;
  t: Translate;
  disabled: boolean;
  onToggleActive: (userId: string, currentStatus: boolean) => void;
  onDelete: (userId: string, userEmail: string) => void;
  onErase: (userId: string, userEmail: string) => void;
}) {
  const toggleLabel = user.is_active
    ? t('settings.admin.users.actions.deactivate')
    : t('settings.admin.users.actions.activate');
  return (
    <div className="flex gap-2">
      {/* Activate/Deactivate: hidden for deleted users (data purged, irreversible) */}
      {!user.is_deleted && (
        <Button
          variant={user.is_active ? 'destructive' : 'success'}
          size="sm"
          onClick={() => onToggleActive(user.id, user.is_active)}
          disabled={disabled}
          className="min-w-[80px] justify-center"
          aria-label={`${toggleLabel} ${user.email}`}
        >
          {toggleLabel}
        </Button>
      )}
      {/* Delete: only for deactivated, non-deleted, non-superuser */}
      {!user.is_superuser && !user.is_active && !user.is_deleted && (
        <Button
          variant="destructive"
          size="sm"
          onClick={() => onDelete(user.id, user.email)}
          disabled={disabled}
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
          onClick={() => onErase(user.id, user.email)}
          disabled={disabled}
          className="min-w-[80px] justify-center"
          aria-label={`${t('settings.admin.users.actions.erase')} ${user.email}`}
        >
          {t('settings.admin.users.actions.erase')}
        </Button>
      )}
    </div>
  );
}

/** One account, in the column order the header declares. */
function UserRow({
  user,
  lng,
  t,
  actions,
}: {
  user: AdminUserRow;
  lng: Language;
  t: Translate;
  actions: ReactNode;
}) {
  const locale = LOCALE_MAP[lng];
  const created = new Date(user.created_at);
  return (
    <tr className="group transition-colors hover:bg-muted/30">
      <td className={cn('px-4 py-3 text-sm text-foreground', EMAIL_FROZEN, FROZEN_BODY_BG)}>
        <div className="w-[var(--admin-email-w)] truncate" title={user.email}>
          {user.email}
        </div>
      </td>
      <td className={cn('px-4 py-3 text-sm text-foreground', NAME_FROZEN, FROZEN_BODY_BG)}>
        <div className="w-[var(--admin-name-w)] truncate" title={user.full_name ?? undefined}>
          {user.full_name || '-'}
        </div>
      </td>
      <td className="whitespace-nowrap px-4 py-3 text-sm text-muted-foreground">
        <time dateTime={user.created_at} title={created.toLocaleString(locale)}>
          {created.toLocaleDateString(locale, {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
          })}
        </time>
      </td>
      <td className="whitespace-nowrap px-3 py-3 text-center text-sm">
        <span className="text-xs font-medium text-muted-foreground">
          {LANGUAGE_CODES[user.language] || user.language}
        </span>
      </td>
      <td className="whitespace-nowrap px-4 py-3 text-sm">
        <UserStatusBadge user={user} t={t} />
        {user.is_superuser && <span className="ml-1 text-xs font-semibold text-primary">★</span>}
      </td>
      <FlagCell on={user.is_usage_blocked} icon={ShieldOff} tone="text-destructive" t={t} />
      {ADMIN_USER_COUNT_COLUMNS.map(column => {
        const count = user[column.key];
        const activeTone =
          column.key === 'active_connectors_count' ? 'text-success' : 'text-primary';
        return (
          <td key={column.key} className="whitespace-nowrap px-3 py-3 text-center">
            <span
              className={cn(
                'text-sm font-medium tabular-nums',
                count > 0 ? activeTone : 'text-muted-foreground'
              )}
            >
              {count}
            </span>
          </td>
        );
      })}
      <td className="whitespace-nowrap px-4 py-3 text-sm">{actions}</td>
      <td className="whitespace-nowrap px-4 py-3 text-sm text-muted-foreground">
        {user.last_message_at ? (
          <span title={new Date(user.last_message_at).toLocaleString(locale)}>
            {new Date(user.last_message_at).toLocaleDateString(locale, {
              day: '2-digit',
              month: '2-digit',
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
        ) : (
          <span className="text-muted-foreground">-</span>
        )}
      </td>
      {ADMIN_USER_STAT_COLUMNS.map(column => (
        <td
          key={column.key}
          className={cn(
            'whitespace-nowrap px-3 py-3 text-right text-sm tabular-nums',
            STAT_WEIGHT[column.weight]
          )}
        >
          {formatStat(user[column.key], column.kind, locale)}
        </td>
      ))}
      {ADMIN_USER_SWITCHES.map(key => (
        <FlagCell
          key={key}
          on={user[key]}
          icon={ADMIN_USER_SWITCH_ICONS[key]}
          tone="text-success"
          t={t}
        />
      ))}
    </tr>
  );
}
