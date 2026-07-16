'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { User, X, Search, Loader2 } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { useTranslation } from '@/i18n/client';
import { logger } from '@/lib/logger';
import { useDebounce } from '@/hooks/useDebounce';
import { cn } from '@/lib/utils';
import type { Language } from '@/i18n/settings';

export interface UserSuggestion {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
}

interface AdminUserAutocompleteProps {
  lng: Language;
  /** i18n key prefix (e.g. 'settings.admin.export'). */
  i18n: string;
  /** DOM id prefix shared with the parent's label htmlFor. */
  idPrefix: string;
  selectedUser: UserSuggestion | null;
  onSelect: (user: UserSuggestion) => void;
  onClear: () => void;
}

/**
 * Admin user filter — a WAI-ARIA combobox/listbox over the user autocomplete API
 * (F014). Extracted from ConsumptionExportSection so that component's cyclomatic
 * complexity stays under the ratchet, and so the stale-response guard + keyboard
 * navigation live in one cohesive, independently tested unit.
 *
 * Stale-response safety: each query fires under its own AbortController; a
 * superseded request is aborted on the effect's cleanup and every shared-state
 * write is gated on ``signal.aborted`` (including in error/finally), so a slow
 * older response can never overwrite fresher suggestions.
 */
export function AdminUserAutocomplete({
  lng,
  i18n,
  idPrefix,
  selectedUser,
  onSelect,
  onClear,
}: AdminUserAutocompleteProps) {
  const { t } = useTranslation(lng, 'translation');

  const [userQuery, setUserQuery] = useState('');
  const [userSuggestions, setUserSuggestions] = useState<UserSuggestion[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const debouncedQuery = useDebounce(userQuery, 300);

  const listboxId = `${idPrefix}-user-listbox`;
  const optionId = (index: number) => `${idPrefix}-user-option-${index}`;

  useEffect(() => {
    if (debouncedQuery.length < 2) {
      setUserSuggestions([]);
      setActiveIndex(-1);
      return;
    }

    const controller = new AbortController();
    setLoadingUsers(true);

    const fetchUsers = async () => {
      try {
        const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || '';
        const response = await fetch(
          `${API_BASE_URL}/api/v1/users/admin/autocomplete?q=${encodeURIComponent(debouncedQuery)}`,
          { credentials: 'include', signal: controller.signal }
        );

        if (controller.signal.aborted) return;
        if (response.ok) {
          const data = await response.json();
          if (controller.signal.aborted) return;
          setUserSuggestions(data.users || []);
          setActiveIndex(-1);
          setShowDropdown(true);
        }
      } catch (error) {
        if ((error as Error).name === 'AbortError') return; // superseded request, ignore
        logger.error('Failed to fetch user suggestions', error as Error);
      } finally {
        if (!controller.signal.aborted) setLoadingUsers(false);
      }
    };

    fetchUsers();
    return () => controller.abort();
  }, [debouncedQuery]);

  // Close the listbox on an outside click.
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelectUser = useCallback(
    (user: UserSuggestion) => {
      setUserQuery('');
      setShowDropdown(false);
      setUserSuggestions([]);
      setActiveIndex(-1);
      onSelect(user);
    },
    [onSelect]
  );

  const handleClearUser = useCallback(() => {
    setUserQuery('');
    setActiveIndex(-1);
    onClear();
    inputRef.current?.focus();
  }, [onClear]);

  const handleInputKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      const count = userSuggestions.length;
      if (count === 0) return;
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          setShowDropdown(true);
          setActiveIndex(i => (i + 1) % count);
          break;
        case 'ArrowUp':
          e.preventDefault();
          setShowDropdown(true);
          setActiveIndex(i => (i <= 0 ? count - 1 : i - 1));
          break;
        case 'Enter':
          if (showDropdown && activeIndex >= 0 && activeIndex < count) {
            e.preventDefault();
            handleSelectUser(userSuggestions[activeIndex]);
          }
          break;
        case 'Escape':
          if (showDropdown) {
            e.preventDefault();
            setShowDropdown(false);
            setActiveIndex(-1);
          }
          break;
      }
    },
    [userSuggestions, showDropdown, activeIndex, handleSelectUser]
  );

  if (selectedUser) {
    return (
      <div ref={dropdownRef} className="relative">
        <div className="flex items-center gap-2 p-2 border border-border rounded-md bg-muted/50">
          <User className="h-4 w-4 text-muted-foreground shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium truncate">{selectedUser.email}</div>
            {selectedUser.full_name && (
              <div className="text-xs text-muted-foreground truncate">{selectedUser.full_name}</div>
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
      </div>
    );
  }

  return (
    <div ref={dropdownRef} className="relative">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          ref={inputRef}
          id={`${idPrefix}-user-filter`}
          type="text"
          role="combobox"
          aria-expanded={showDropdown && userSuggestions.length > 0}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-activedescendant={activeIndex >= 0 ? optionId(activeIndex) : undefined}
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
          onKeyDown={handleInputKeyDown}
          placeholder={t(`${i18n}.user_placeholder`)}
          className="pl-10 pr-8"
        />
        {loadingUsers && (
          <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground animate-spin" />
        )}
      </div>

      {showDropdown && userSuggestions.length > 0 && (
        <ul
          id={listboxId}
          role="listbox"
          aria-label={t(`${i18n}.user_filter`)}
          className="absolute z-10 w-full mt-1 bg-popover border border-border rounded-md shadow-lg max-h-60 overflow-auto"
        >
          {userSuggestions.map((user, index) => (
            <li
              key={user.id}
              id={optionId(index)}
              role="option"
              aria-selected={index === activeIndex}
              // mousedown (not click) selects before the input blurs / the
              // outside-click handler fires, keeping focus on the input.
              onMouseDown={e => {
                e.preventDefault();
                handleSelectUser(user);
              }}
              onMouseEnter={() => setActiveIndex(index)}
              className={cn(
                'w-full px-3 py-2 text-left flex items-center gap-2 cursor-pointer',
                index === activeIndex ? 'bg-muted' : 'hover:bg-muted',
                !user.is_active && 'opacity-60'
              )}
            >
              <User className="h-4 w-4 text-muted-foreground shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="text-sm truncate">{user.email}</div>
                {user.full_name && (
                  <div className="text-xs text-muted-foreground truncate">{user.full_name}</div>
                )}
              </div>
              {!user.is_active && (
                <span className="text-xs text-muted-foreground">({t(`${i18n}.inactive`)})</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
