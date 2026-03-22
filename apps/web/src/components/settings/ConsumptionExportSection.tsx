'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { toast } from 'sonner';
import { Download, FileSpreadsheet, Calendar, User, X, Search, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useTranslation } from '@/i18n/client';
import { SettingsSection } from '@/components/settings/SettingsSection';
import type { BaseSettingsProps } from '@/types/settings';
import { logger } from '@/lib/logger';
import { useDebounce } from '@/hooks/useDebounce';
import { cn } from '@/lib/utils';

type ExportType = 'token-usage' | 'google-api-usage' | 'consumption-summary';

interface UserSuggestion {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
}

interface ConsumptionExportSectionProps extends BaseSettingsProps {
  /** 'admin' shows user filter and uses admin endpoint; 'user' exports own data only. */
  mode: 'admin' | 'user';
}

const ENDPOINT_BASE: Record<ConsumptionExportSectionProps['mode'], string> = {
  admin: '/api/v1/admin/google-api/export',
  user: '/api/v1/usage/export',
};

const I18N_PREFIX: Record<ConsumptionExportSectionProps['mode'], string> = {
  admin: 'settings.admin.export',
  user: 'settings.user.export',
};

export default function ConsumptionExportSection({
  lng,
  collapsible = true,
  mode,
}: ConsumptionExportSectionProps) {
  const { t } = useTranslation(lng, 'translation');
  const i18n = I18N_PREFIX[mode];

  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [exporting, setExporting] = useState<ExportType | null>(null);

  // User autocomplete state (admin mode only)
  const [userQuery, setUserQuery] = useState('');
  const [userSuggestions, setUserSuggestions] = useState<UserSuggestion[]>([]);
  const [selectedUser, setSelectedUser] = useState<UserSuggestion | null>(null);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const debouncedQuery = useDebounce(userQuery, 300);

  // Get today and first day of current month for defaults
  const today = new Date().toISOString().split('T')[0];
  const firstDayOfMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1)
    .toISOString()
    .split('T')[0];

  // Fetch user suggestions when query changes (admin mode only)
  useEffect(() => {
    if (mode !== 'admin') return;

    const fetchUsers = async () => {
      if (debouncedQuery.length < 2) {
        setUserSuggestions([]);
        return;
      }

      setLoadingUsers(true);
      try {
        const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || '';
        const response = await fetch(
          `${API_BASE_URL}/api/v1/users/admin/autocomplete?q=${encodeURIComponent(debouncedQuery)}`,
          { credentials: 'include' }
        );

        if (response.ok) {
          const data = await response.json();
          setUserSuggestions(data.users || []);
          setShowDropdown(true);
        }
      } catch (error) {
        logger.error('Failed to fetch user suggestions', error as Error);
      } finally {
        setLoadingUsers(false);
      }
    };

    fetchUsers();
  }, [debouncedQuery, mode]);

  // Close dropdown when clicking outside
  useEffect(() => {
    if (mode !== 'admin') return;

    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowDropdown(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [mode]);

  const handleSelectUser = useCallback((user: UserSuggestion) => {
    setSelectedUser(user);
    setUserQuery('');
    setShowDropdown(false);
    setUserSuggestions([]);
  }, []);

  const handleClearUser = useCallback(() => {
    setSelectedUser(null);
    setUserQuery('');
    inputRef.current?.focus();
  }, []);

  const handleExport = async (exportType: ExportType) => {
    setExporting(exportType);

    try {
      // Build URL with query params
      const params = new URLSearchParams();
      if (startDate) params.append('start_date', startDate);
      if (endDate) params.append('end_date', endDate);
      // Only admin mode can filter by user — user mode never sends user_id
      if (mode === 'admin' && selectedUser) params.append('user_id', selectedUser.id);

      const endpoint = `${ENDPOINT_BASE[mode]}/${exportType}`;
      const url = `${process.env.NEXT_PUBLIC_API_URL}${endpoint}?${params.toString()}`;

      // Fetch with credentials (for auth cookie)
      const response = await fetch(url, {
        method: 'GET',
        credentials: 'include',
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Export failed with status ${response.status}`);
      }

      // Get filename from Content-Disposition header
      const contentDisposition = response.headers.get('Content-Disposition');
      const filenameMatch = contentDisposition?.match(/filename="(.+)"/);
      const filename = filenameMatch ? filenameMatch[1] : `${exportType}_export.csv`;

      // Download the file
      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(downloadUrl);

      toast.success(t(`${i18n}.success`));
    } catch (error) {
      logger.error('Export failed', error as Error, {
        component: 'ConsumptionExportSection',
        mode,
        exportType,
        startDate,
        endDate,
        userId: selectedUser?.id,
      });
      toast.error(t(`${i18n}.error`));
    } finally {
      setExporting(null);
    }
  };

  const isAdmin = mode === 'admin';
  const dateGridCols = isAdmin ? 'sm:grid-cols-3' : 'sm:grid-cols-2';
  const idPrefix = `${mode}-export`;

  const content = (
    <div className="space-y-6">
      {/* Quick date presets */}
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            const now = new Date();
            const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
            setStartDate(firstDay.toISOString().split('T')[0]);
            setEndDate(now.toISOString().split('T')[0]);
          }}
        >
          {t(`${i18n}.preset_current_month`)}
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            const now = new Date();
            const firstDay = new Date(now.getFullYear(), now.getMonth() - 1, 1);
            const lastDay = new Date(now.getFullYear(), now.getMonth(), 0);
            setStartDate(firstDay.toISOString().split('T')[0]);
            setEndDate(lastDay.toISOString().split('T')[0]);
          }}
        >
          {t(`${i18n}.preset_last_month`)}
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            const now = new Date();
            const last30Days = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
            setStartDate(last30Days.toISOString().split('T')[0]);
            setEndDate(now.toISOString().split('T')[0]);
          }}
        >
          {t(`${i18n}.preset_last_30_days`)}
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            setStartDate('');
            setEndDate('');
          }}
        >
          {t(`${i18n}.preset_all_time`)}
        </Button>
      </div>

      {/* Filters Row */}
      <div className={`grid gap-4 ${dateGridCols} min-w-0`}>
        {/* User Filter with Autocomplete (admin mode only) */}
        {isAdmin && (
          <div className="sm:col-span-1 min-w-0" ref={dropdownRef}>
            <label
              htmlFor={`${idPrefix}-user-filter`}
              className="block text-sm font-medium text-foreground mb-1"
            >
              {t(`${i18n}.user_filter`)}
            </label>
            <div className="relative">
              {selectedUser ? (
                // Selected user display
                <div className="flex items-center gap-2 p-2 border border-border rounded-md bg-muted/50">
                  <User className="h-4 w-4 text-muted-foreground shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium truncate">{selectedUser.email}</div>
                    {selectedUser.full_name && (
                      <div className="text-xs text-muted-foreground truncate">
                        {selectedUser.full_name}
                      </div>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={handleClearUser}
                    className="p-1 hover:bg-muted rounded"
                    aria-label={t(`${i18n}.clear_user`)}
                  >
                    <X className="h-4 w-4 text-muted-foreground" />
                  </button>
                </div>
              ) : (
                // Search input
                <>
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      ref={inputRef}
                      id={`${idPrefix}-user-filter`}
                      type="text"
                      value={userQuery}
                      onChange={e => {
                        setUserQuery(e.target.value);
                        if (e.target.value.length >= 2) {
                          setShowDropdown(true);
                        }
                      }}
                      onFocus={() => {
                        if (userSuggestions.length > 0) {
                          setShowDropdown(true);
                        }
                      }}
                      placeholder={t(`${i18n}.user_placeholder`)}
                      className="pl-10 pr-8"
                    />
                    {loadingUsers && (
                      <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground animate-spin" />
                    )}
                  </div>

                  {/* Dropdown suggestions */}
                  {showDropdown && userSuggestions.length > 0 && (
                    <div className="absolute z-10 w-full mt-1 bg-popover border border-border rounded-md shadow-lg max-h-60 overflow-auto">
                      {userSuggestions.map(user => (
                        <button
                          key={user.id}
                          type="button"
                          onClick={() => handleSelectUser(user)}
                          className={cn(
                            'w-full px-3 py-2 text-left hover:bg-muted flex items-center gap-2',
                            !user.is_active && 'opacity-60'
                          )}
                        >
                          <User className="h-4 w-4 text-muted-foreground shrink-0" />
                          <div className="flex-1 min-w-0">
                            <div className="text-sm truncate">{user.email}</div>
                            {user.full_name && (
                              <div className="text-xs text-muted-foreground truncate">
                                {user.full_name}
                              </div>
                            )}
                          </div>
                          {!user.is_active && (
                            <span className="text-xs text-muted-foreground">
                              ({t(`${i18n}.inactive`)})
                            </span>
                          )}
                        </button>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-1">{t(`${i18n}.user_filter_hint`)}</p>
          </div>
        )}

        {/* Date Filters */}
        <div className="min-w-0 overflow-hidden">
          <label
            htmlFor={`${idPrefix}-start-date`}
            className="block text-sm font-medium text-foreground mb-1"
          >
            {t(`${i18n}.start_date`)}
          </label>
          <div className="relative min-w-0">
            <Input
              id={`${idPrefix}-start-date`}
              type="date"
              value={startDate}
              onChange={e => setStartDate(e.target.value)}
              placeholder={firstDayOfMonth}
              className="pl-10 w-full min-w-0"
            />
            <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
          </div>
        </div>
        <div className="min-w-0 overflow-hidden">
          <label
            htmlFor={`${idPrefix}-end-date`}
            className="block text-sm font-medium text-foreground mb-1"
          >
            {t(`${i18n}.end_date`)}
          </label>
          <div className="relative min-w-0">
            <Input
              id={`${idPrefix}-end-date`}
              type="date"
              value={endDate}
              onChange={e => setEndDate(e.target.value)}
              placeholder={today}
              className="pl-10 w-full min-w-0"
            />
            <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
          </div>
        </div>
      </div>

      {/* Export Buttons */}
      <div className="grid gap-4 sm:grid-cols-3">
        {/* Token Usage Export */}
        <div className="p-4 border border-border rounded-lg bg-card">
          <div className="flex items-center gap-2 mb-2">
            <FileSpreadsheet className="h-5 w-5 text-primary" />
            <h4 className="font-medium">{t(`${i18n}.token_usage_title`)}</h4>
          </div>
          <p className="text-sm text-muted-foreground mb-4">
            {t(`${i18n}.token_usage_description`)}
          </p>
          <Button
            onClick={() => handleExport('token-usage')}
            disabled={exporting !== null}
            className="w-full"
          >
            {exporting === 'token-usage' ? (
              <span className="animate-pulse">{t(`${i18n}.exporting`)}</span>
            ) : (
              <>
                <Download className="h-4 w-4 mr-2" />
                {t(`${i18n}.download_csv`)}
              </>
            )}
          </Button>
        </div>

        {/* Google API Usage Export */}
        <div className="p-4 border border-border rounded-lg bg-card">
          <div className="flex items-center gap-2 mb-2">
            <FileSpreadsheet className="h-5 w-5 text-primary" />
            <h4 className="font-medium">{t(`${i18n}.google_api_usage_title`)}</h4>
          </div>
          <p className="text-sm text-muted-foreground mb-4">
            {t(`${i18n}.google_api_usage_description`)}
          </p>
          <Button
            onClick={() => handleExport('google-api-usage')}
            disabled={exporting !== null}
            className="w-full"
          >
            {exporting === 'google-api-usage' ? (
              <span className="animate-pulse">{t(`${i18n}.exporting`)}</span>
            ) : (
              <>
                <Download className="h-4 w-4 mr-2" />
                {t(`${i18n}.download_csv`)}
              </>
            )}
          </Button>
        </div>

        {/* Consumption Summary Export */}
        <div className="p-4 border border-border rounded-lg bg-card">
          <div className="flex items-center gap-2 mb-2">
            <FileSpreadsheet className="h-5 w-5 text-primary" />
            <h4 className="font-medium">{t(`${i18n}.summary_title`)}</h4>
          </div>
          <p className="text-sm text-muted-foreground mb-4">{t(`${i18n}.summary_description`)}</p>
          <Button
            onClick={() => handleExport('consumption-summary')}
            disabled={exporting !== null}
            className="w-full"
          >
            {exporting === 'consumption-summary' ? (
              <span className="animate-pulse">{t(`${i18n}.exporting`)}</span>
            ) : (
              <>
                <Download className="h-4 w-4 mr-2" />
                {t(`${i18n}.download_csv`)}
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  );

  const sectionValue = mode === 'admin' ? 'admin-consumption-export' : 'user-consumption-export';

  return (
    <SettingsSection
      value={sectionValue}
      title={t(`${i18n}.title`)}
      description={t(`${i18n}.description`)}
      icon={FileSpreadsheet}
      collapsible={collapsible}
    >
      {content}
    </SettingsSection>
  );
}
