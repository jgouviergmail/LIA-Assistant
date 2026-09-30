'use client';

import { useEffect, useRef } from 'react';

import { isValidFontFamily, isValidFontSize } from '@/constants/fonts';
import { useAuth } from '@/hooks/useAuth';
import { useFontFamily } from '@/lib/font-context';

/**
 * Applies the account's font family and text size on every authenticated page.
 *
 * The device keeps its own copy (localStorage, applied before paint); the
 * account is the authority once it is known, so a choice made on one device
 * reaches the others. Mounted once, inside `AuthProvider`. Renders nothing.
 *
 * Each value is applied when the ACCOUNT value changes, never when the local
 * one does: a choice the save has not echoed back yet must not be undone by
 * the account value it is about to replace.
 */
export function FontPreferencesSync() {
  const { user } = useAuth();
  const { fontFamily, setFontFamily, fontSize, setFontSize } = useFontFamily();
  const accountFamily = user?.font_family;
  const accountSize = user?.font_size;
  const appliedFamily = useRef<string | undefined>(undefined);
  const appliedSize = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (accountFamily === appliedFamily.current) return;
    appliedFamily.current = accountFamily;
    if (accountFamily && isValidFontFamily(accountFamily) && accountFamily !== fontFamily) {
      setFontFamily(accountFamily);
    }
  }, [accountFamily, fontFamily, setFontFamily]);

  useEffect(() => {
    if (accountSize === appliedSize.current) return;
    appliedSize.current = accountSize;
    if (isValidFontSize(accountSize) && accountSize !== fontSize) {
      setFontSize(accountSize);
    }
  }, [accountSize, fontSize, setFontSize]);

  return null;
}
