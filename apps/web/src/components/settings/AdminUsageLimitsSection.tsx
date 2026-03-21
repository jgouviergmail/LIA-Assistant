'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Gauge, Search, Shield, ShieldOff } from 'lucide-react';
import { toast } from 'sonner';

import { apiClient, ApiError } from '@/lib/api-client';
import { logger } from '@/lib/logger';
import { formatEuro } from '@/lib/format';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { UsageGauge } from '@/components/usage/UsageGauge';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { AdminUsageLimitsEditModal } from '@/components/settings/AdminUsageLimitsEditModal';
import type {
  AdminUsageLimitsListResponse,
  AdminUserUsageLimitResponse,
} from '@/types/usage-limits';

const PAGE_SIZE = 20;

interface AdminUsageLimitsSectionProps {
  lng: string;
}

/**
 * Admin section for managing per-user usage limits.
 *
 * Displays a searchable, paginated table of all users with their
 * limits configuration and current usage gauges.
 * Supports inline block toggle and modal-based limit editing.
 */
export function AdminUsageLimitsSection({ lng: _lng }: AdminUsageLimitsSectionProps) {
  const { t } = useTranslation();

  // State
  const [users, setUsers] = useState<AdminUserUsageLimitResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [editUser, setEditUser] = useState<AdminUserUsageLimitResponse | null>(null);
  const [featureDisabled, setFeatureDisabled] = useState(false);

  // Fetch users
  const fetchUsers = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string | number> = {
        page,
        page_size: PAGE_SIZE,
      };
      if (search) params.search = search;

      const response = await apiClient.get<AdminUsageLimitsListResponse>(
        '/usage-limits/admin/users',
        { params }
      );
      setUsers(response.users);
      setTotal(response.total);
      setTotalPages(response.total_pages);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        // Feature disabled (router not registered) — hide section
        setFeatureDisabled(true);
        return;
      }
      logger.error('Failed to fetch usage limits', err as Error, {
        component: 'AdminUsageLimitsSection',
      });
      toast.error(t('usage_limits.error.loading'));
    } finally {
      setLoading(false);
    }
  }, [page, search, t]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  // Search debounce
  const [searchInput, setSearchInput] = useState('');
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Block toggle handler with optimistic update and revert on error
  const handleBlockToggle = async (user: AdminUserUsageLimitResponse) => {
    const newBlocked = !user.is_usage_blocked;
    const previousUsers = [...users];

    // Optimistic update
    setUsers(prev =>
      prev.map(u => (u.user_id === user.user_id ? { ...u, is_usage_blocked: newBlocked } : u))
    );

    try {
      const updated = await apiClient.put<AdminUserUsageLimitResponse>(
        `/usage-limits/admin/users/${user.user_id}/block`,
        {
          is_usage_blocked: newBlocked,
          blocked_reason: newBlocked ? t('usage_limits.edit.default_block_reason') : null,
        }
      );
      // Merge server response into local state (no full refetch → no focus loss)
      setUsers(prev => prev.map(u => (u.user_id === updated.user_id ? updated : u)));
    } catch (err) {
      // Revert optimistic update
      setUsers(previousUsers);
      logger.error('Usage limit block toggle failed', err as Error, {
        component: 'AdminUsageLimitsSection',
      });
      toast.error(t('usage_limits.edit.error'));
    }
  };

  // Modal save handler — merge updated user into local state (no full refetch)
  const handleSave = async (updatedUser?: AdminUserUsageLimitResponse) => {
    setEditUser(null);
    if (updatedUser) {
      setUsers(prev => prev.map(u => (u.user_id === updatedUser.user_id ? updatedUser : u)));
    }
    toast.success(t('usage_limits.edit.success'));
  };

  // Helper to build LimitDetail for inline gauges
  const buildDetail = (current: number, limit: number | null) => ({
    current,
    limit,
    usage_pct: limit !== null && limit > 0 ? (current / limit) * 100 : null,
    exceeded: limit !== null && current >= limit,
  });

  // Don't render if feature is disabled (404 from backend)
  if (featureDisabled) return null;

  return (
    <SettingsSection
      value="admin-usage-limits"
      title={t('usage_limits.title')}
      description={t('usage_limits.description')}
      icon={Gauge}
      collapsible
    >
      {/* Search */}
      <div className="relative mb-4">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder={t('usage_limits.search_placeholder')}
          value={searchInput}
          onChange={e => setSearchInput(e.target.value)}
          className="pl-9"
        />
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th className="pb-2 pr-3 font-medium w-40">{t('usage_limits.table.email')}</th>
              <th className="pb-2 pr-3 font-medium">{t('usage_limits.table.tokens')}</th>
              <th className="pb-2 pr-3 font-medium">{t('usage_limits.table.messages')}</th>
              <th className="pb-2 pr-3 font-medium">{t('usage_limits.table.cost')}</th>
              <th className="pb-2 pr-2 font-medium w-12 text-center">
                {t('usage_limits.table.blocked')}
              </th>
              <th className="pb-2 font-medium w-20">{t('usage_limits.table.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} className="py-8 text-center text-muted-foreground">
                  {t('common.loading')}
                </td>
              </tr>
            ) : users.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-8 text-center text-muted-foreground">
                  {t('usage_limits.table.no_results')}
                </td>
              </tr>
            ) : (
              users.map(user => (
                <tr key={user.user_id} className="border-b border-border/50 hover:bg-muted/30">
                  <td className="py-2 pr-3 w-40">
                    <div className="font-medium truncate max-w-[10rem]" title={user.email}>
                      {user.email}
                    </div>
                    {user.full_name && (
                      <div className="text-muted-foreground truncate max-w-[10rem]">
                        {user.full_name}
                      </div>
                    )}
                  </td>
                  <td className="py-2 pr-3 w-52">
                    {/* Cycle tokens */}
                    {user.token_limit_per_cycle !== null && (
                      <UsageGauge
                        detail={buildDetail(user.cycle_tokens, user.token_limit_per_cycle)}
                        label={t('usage_limits.mode.period')}
                        mode="period"
                        t={t}
                        size="sm"
                      />
                    )}
                    {/* Absolute tokens */}
                    {user.token_limit_absolute !== null && (
                      <div className={user.token_limit_per_cycle !== null ? 'mt-2' : ''}>
                        <UsageGauge
                          detail={buildDetail(user.total_tokens, user.token_limit_absolute)}
                          label={t('usage_limits.mode.absolute')}
                          mode="absolute"
                          t={t}
                          size="sm"
                        />
                      </div>
                    )}
                    {/* Both unlimited */}
                    {user.token_limit_per_cycle === null && user.token_limit_absolute === null && (
                      <span className="text-muted-foreground">{t('usage_limits.unlimited')}</span>
                    )}
                  </td>
                  <td className="py-2 pr-3 w-52">
                    {user.message_limit_per_cycle !== null && (
                      <UsageGauge
                        detail={buildDetail(user.cycle_messages, user.message_limit_per_cycle)}
                        label={t('usage_limits.mode.period')}
                        mode="period"
                        t={t}
                        size="sm"
                      />
                    )}
                    {user.message_limit_absolute !== null && (
                      <div className={user.message_limit_per_cycle !== null ? 'mt-2' : ''}>
                        <UsageGauge
                          detail={buildDetail(user.total_messages, user.message_limit_absolute)}
                          label={t('usage_limits.mode.absolute')}
                          mode="absolute"
                          t={t}
                          size="sm"
                        />
                      </div>
                    )}
                    {user.message_limit_per_cycle === null &&
                      user.message_limit_absolute === null && (
                        <span className="text-muted-foreground">{t('usage_limits.unlimited')}</span>
                      )}
                  </td>
                  <td className="py-2 pr-3 w-52">
                    {user.cost_limit_per_cycle !== null && (
                      <UsageGauge
                        detail={buildDetail(user.cycle_cost, user.cost_limit_per_cycle)}
                        label={t('usage_limits.mode.period')}
                        mode="period"
                        formatValue={v => formatEuro(v, 2)}
                        t={t}
                        size="sm"
                      />
                    )}
                    {user.cost_limit_absolute !== null && (
                      <div className={user.cost_limit_per_cycle !== null ? 'mt-2' : ''}>
                        <UsageGauge
                          detail={buildDetail(user.total_cost, user.cost_limit_absolute)}
                          label={t('usage_limits.mode.absolute')}
                          mode="absolute"
                          formatValue={v => formatEuro(v, 2)}
                          t={t}
                          size="sm"
                        />
                      </div>
                    )}
                    {user.cost_limit_per_cycle === null && user.cost_limit_absolute === null && (
                      <span className="text-muted-foreground">{t('usage_limits.unlimited')}</span>
                    )}
                  </td>
                  <td className="py-2 pr-3">
                    <button
                      onClick={() => handleBlockToggle(user)}
                      disabled={loading}
                      aria-label={
                        user.is_usage_blocked
                          ? t('usage_limits.table.unblock')
                          : t('usage_limits.table.block')
                      }
                      className={`p-1.5 rounded-md transition-colors ${
                        user.is_usage_blocked
                          ? 'bg-destructive/10 text-destructive hover:bg-destructive/20'
                          : 'bg-muted text-muted-foreground hover:bg-muted/80'
                      }`}
                      title={
                        user.is_usage_blocked
                          ? t('usage_limits.table.unblock')
                          : t('usage_limits.table.block')
                      }
                    >
                      {user.is_usage_blocked ? (
                        <ShieldOff className="h-4 w-4" />
                      ) : (
                        <Shield className="h-4 w-4" />
                      )}
                    </button>
                  </td>
                  <td className="py-2">
                    <Button variant="outline" size="sm" onClick={() => setEditUser(user)}>
                      {t('usage_limits.table.edit')}
                    </Button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4 text-xs text-muted-foreground">
          <span>{t('usage_limits.table.page_info', { page, totalPages, total })}</span>
          <div className="flex gap-1">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1 || loading}
              onClick={() => setPage(p => p - 1)}
            >
              {t('common.previous')}
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages || loading}
              onClick={() => setPage(p => p + 1)}
            >
              {t('common.next')}
            </Button>
          </div>
        </div>
      )}

      {/* Edit Modal */}
      {editUser && (
        <AdminUsageLimitsEditModal
          user={editUser}
          open={!!editUser}
          onClose={() => setEditUser(null)}
          onSave={handleSave}
        />
      )}
    </SettingsSection>
  );
}
