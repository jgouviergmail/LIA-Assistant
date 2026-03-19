'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Megaphone, Send, X, Users, UserCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useDebounce } from '@/hooks/useDebounce';
import { useTranslation } from '@/i18n/client';
import { SettingsSection } from '@/components/settings/SettingsSection';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import type { BaseSettingsProps } from '@/types/settings';

interface BroadcastRequest {
  message: string;
  expires_in_days: number | null;
  user_ids: string[] | null;
}

interface BroadcastResponse {
  success: boolean;
  broadcast_id: string;
  total_users: number;
  fcm_sent: number;
  fcm_failed: number;
}

interface UserAutocompleteItem {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
}

interface UserAutocompleteResponse {
  users: UserAutocompleteItem[];
  total: number;
}

/**
 * Admin section for sending broadcast messages to users.
 *
 * Features:
 * - Text input with character limit (1000 chars)
 * - Optional expiration (7, 30, 90 days or never)
 * - User selection: all users or specific users
 * - Autocomplete search for user selection
 * - Confirmation dialog before sending
 * - Success/error toast with delivery stats
 */
export default function AdminBroadcastSection({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const [message, setMessage] = useState('');
  const [expiresInDays, setExpiresInDays] = useState<string>('none');
  const [showConfirm, setShowConfirm] = useState(false);

  // User selection state
  const [sendToAll, setSendToAll] = useState(true);
  const [selectedUsers, setSelectedUsers] = useState<UserAutocompleteItem[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [showDropdown, setShowDropdown] = useState(false);
  const debouncedSearch = useDebounce(searchQuery, 300);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Fetch users from autocomplete API
  const { data: searchResults, loading: searchLoading } = useApiQuery<UserAutocompleteResponse>(
    `/users/admin/autocomplete?q=${encodeURIComponent(debouncedSearch)}`,
    {
      componentName: 'AdminBroadcastSection',
      initialData: { users: [], total: 0 },
      enabled: debouncedSearch.length >= 2,
    }
  );

  const { mutate: sendBroadcast, loading } = useApiMutation<BroadcastRequest, BroadcastResponse>({
    method: 'POST',
    componentName: 'AdminBroadcastSection',
  });

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowDropdown(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelectUser = useCallback((user: UserAutocompleteItem) => {
    // Use functional update to avoid selectedUsers dependency
    setSelectedUsers(prev => {
      if (prev.some(u => u.id === user.id)) {
        return prev; // Already selected, no change
      }
      return [...prev, user];
    });
    setSearchQuery('');
    setShowDropdown(false);
    inputRef.current?.focus();
  }, []);

  const handleRemoveUser = useCallback((userId: string) => {
    setSelectedUsers(prev => prev.filter(u => u.id !== userId));
  }, []);

  const handleSend = async () => {
    setShowConfirm(false);
    try {
      const payload: BroadcastRequest = {
        message,
        expires_in_days: expiresInDays === 'none' ? null : parseInt(expiresInDays, 10),
        user_ids: sendToAll ? null : selectedUsers.map(u => u.id),
      };
      const result = await sendBroadcast('/notifications/admin/broadcast', payload);
      if (result) {
        toast.success(
          t('settings.admin.broadcast.success', {
            total: result.total_users,
            fcm: result.fcm_sent,
          })
        );
        setMessage('');
        setExpiresInDays('none');
        setSelectedUsers([]);
        setSendToAll(true);
      }
    } catch {
      toast.error(t('settings.admin.broadcast.error'));
    }
  };

  // Filter out already selected users AND inactive users from search results
  // (inactive users are ignored by backend anyway, avoid UX confusion)
  const filteredResults =
    searchResults?.users.filter(
      user => user.is_active && !selectedUsers.some(selected => selected.id === user.id)
    ) || [];

  const canSend = message.trim() && (sendToAll || selectedUsers.length > 0);

  return (
    <SettingsSection
      value="admin-broadcast"
      title={t('settings.admin.broadcast.title')}
      description={t('settings.admin.broadcast.description')}
      icon={Megaphone}
      collapsible={collapsible}
    >
      <div className="space-y-8">
        {/* Recipient Selection */}
        <div className="space-y-3">
          <Label>{t('settings.admin.broadcast.recipients')}</Label>

          {/* Toggle: All users vs Selected users */}
          <div className="grid grid-cols-2 gap-2">
            <Button
              type="button"
              variant={sendToAll ? 'default' : 'outline'}
              size="sm"
              onClick={() => setSendToAll(true)}
              className="flex items-center justify-center gap-2"
            >
              <Users className="h-4 w-4" />
              {t('settings.admin.broadcast.all_users')}
            </Button>
            <Button
              type="button"
              variant={!sendToAll ? 'default' : 'outline'}
              size="sm"
              onClick={() => setSendToAll(false)}
              className="flex items-center justify-center gap-2"
            >
              <UserCheck className="h-4 w-4" />
              {t('settings.admin.broadcast.selected_users')}
            </Button>
          </div>

          {/* User Search (only when not sending to all) */}
          {!sendToAll && (
            <div className="space-y-2">
              {/* Selected Users Badges */}
              {selectedUsers.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {selectedUsers.map(user => (
                    <Badge
                      key={user.id}
                      variant="secondary"
                      className="flex items-center gap-1 pr-1"
                    >
                      <span className="max-w-[150px] truncate">{user.full_name || user.email}</span>
                      <button
                        type="button"
                        onClick={() => handleRemoveUser(user.id)}
                        className="ml-1 rounded-full hover:bg-muted p-0.5"
                        aria-label={t('settings.admin.broadcast.remove_user')}
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </Badge>
                  ))}
                </div>
              )}

              {/* Search Input with Dropdown */}
              <div className="relative" ref={dropdownRef}>
                <Input
                  ref={inputRef}
                  type="text"
                  value={searchQuery}
                  onChange={e => {
                    setSearchQuery(e.target.value);
                    setShowDropdown(true);
                  }}
                  onFocus={() => setShowDropdown(true)}
                  placeholder={t('settings.admin.broadcast.search_users')}
                  className="w-full"
                />

                {/* Loading indicator */}
                {searchLoading && searchQuery.length >= 2 && (
                  <div className="absolute right-3 top-1/2 -translate-y-1/2">
                    <LoadingSpinner
                      size="sm"
                      spinnerColor="muted"
                      label={t('settings.admin.broadcast.searching')}
                    />
                  </div>
                )}

                {/* Dropdown Results */}
                {showDropdown && searchQuery.length >= 2 && !searchLoading && (
                  <div className="absolute z-50 w-full mt-1 bg-popover border border-border rounded-md shadow-lg max-h-48 overflow-y-auto">
                    {filteredResults.length > 0 ? (
                      filteredResults.map(user => (
                        <button
                          key={user.id}
                          type="button"
                          onClick={() => handleSelectUser(user)}
                          className="w-full px-3 py-2 text-left hover:bg-accent flex flex-col"
                        >
                          <span className="font-medium text-sm">
                            {user.full_name || user.email}
                          </span>
                          {user.full_name && (
                            <span className="text-xs text-muted-foreground">{user.email}</span>
                          )}
                        </button>
                      ))
                    ) : (
                      <div className="px-3 py-2 text-sm text-muted-foreground">
                        {t('settings.admin.broadcast.no_users_found')}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Selected count */}
              {selectedUsers.length > 0 && (
                <p className="text-xs text-muted-foreground">
                  {t('settings.admin.broadcast.selected_count', { count: selectedUsers.length })}
                </p>
              )}
            </div>
          )}
        </div>

        {/* Message Input */}
        <div className="space-y-2">
          <Label htmlFor="broadcast-message">{t('settings.admin.broadcast.message_label')}</Label>
          <Textarea
            id="broadcast-message"
            value={message}
            onChange={e => setMessage(e.target.value)}
            placeholder={t('settings.admin.broadcast.placeholder')}
            maxLength={1000}
            rows={4}
            className="resize-none"
          />
          <div className="flex justify-end">
            <span className="text-xs text-muted-foreground">{message.length}/1000</span>
          </div>
        </div>

        {/* Expiration and Send Button */}
        <div className="flex flex-col sm:flex-row gap-4 sm:items-end">
          <div className="flex-1 space-y-2">
            <Label htmlFor="broadcast-expires">{t('settings.admin.broadcast.expires')}</Label>
            <Select value={expiresInDays} onValueChange={setExpiresInDays}>
              <SelectTrigger id="broadcast-expires">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">{t('settings.admin.broadcast.never_expires')}</SelectItem>
                <SelectItem value="7">7 {t('common.days')}</SelectItem>
                <SelectItem value="30">30 {t('common.days')}</SelectItem>
                <SelectItem value="90">90 {t('common.days')}</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <Button
            onClick={() => setShowConfirm(true)}
            disabled={loading || !canSend}
            className="sm:w-auto w-full"
          >
            <Send className="h-4 w-4 mr-2" />
            {loading ? t('settings.admin.broadcast.sending') : t('settings.admin.broadcast.send')}
          </Button>
        </div>
      </div>

      {/* Confirmation Dialog */}
      <AlertDialog open={showConfirm} onOpenChange={setShowConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('settings.admin.broadcast.confirm_title')}</AlertDialogTitle>
            <AlertDialogDescription>
              {sendToAll
                ? t('settings.admin.broadcast.confirm_description_all')
                : t('settings.admin.broadcast.confirm_description_selected', {
                    count: selectedUsers.length,
                  })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="my-4 p-4 bg-muted rounded-lg max-h-48 overflow-y-auto">
            <p className="whitespace-pre-wrap text-sm">{message}</p>
          </div>
          {!sendToAll && selectedUsers.length > 0 && (
            <div className="mb-4">
              <p className="text-sm font-medium mb-2">
                {t('settings.admin.broadcast.recipients')}:
              </p>
              <div className="flex flex-wrap gap-1">
                {selectedUsers.map(user => (
                  <Badge key={user.id} variant="secondary" size="sm">
                    {user.full_name || user.email}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleSend}>
              {t('settings.admin.broadcast.confirm_send')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </SettingsSection>
  );
}
