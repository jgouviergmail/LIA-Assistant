'use client';

import { useState, useEffect, useCallback } from 'react';
import { useTheme } from 'next-themes';

const LIA_GENDER_COOKIE = 'lia_gender';

/**
 * Hook to manage LIA's gender preference (masculine/feminine)
 * Persisted in a cookie for 1 year.
 * Used on both the dashboard page (with toggle) and chat page (background).
 */
export function useLiaGender() {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [isMale, setIsMale] = useState(false);

  useEffect(() => {
    setMounted(true);
    // Read gender preference from cookie
    const cookies = document.cookie.split(';');
    const genderCookie = cookies.find(c => c.trim().startsWith(`${LIA_GENDER_COOKIE}=`));
    if (genderCookie) {
      const value = genderCookie.split('=')[1];
      setIsMale(value === 'male');
    }
  }, []);

  const toggleGender = useCallback(() => {
    const newIsMale = !isMale;
    setIsMale(newIsMale);
    // Save preference in cookie (1 year expiry)
    const expires = new Date();
    expires.setFullYear(expires.getFullYear() + 1);
    document.cookie = `${LIA_GENDER_COOKIE}=${newIsMale ? 'male' : 'female'}; expires=${expires.toUTCString()}; path=/`;
  }, [isMale]);

  // LIA images: TC/TS for female, TCM/TSM for male
  // TC = clair (light), TS = sombre (dark)
  const getLiaImage = useCallback(() => {
    if (!mounted) return '/LIA_TC.jpg';
    const isDark = resolvedTheme === 'dark';
    if (isDark) {
      return isMale ? '/LIA_TSM.jpg' : '/LIA_TS.jpg';
    }
    return isMale ? '/LIA_TCM.jpg' : '/LIA_TC.jpg';
  }, [mounted, resolvedTheme, isMale]);

  // Background images for chat screen: _BG variants
  const getLiaBackgroundImage = useCallback(() => {
    if (!mounted) return '/LIA_TC_BG.jpg';
    const isDark = resolvedTheme === 'dark';
    if (isDark) {
      return isMale ? '/LIA_TSM_BG.jpg' : '/LIA_TS_BG.jpg';
    }
    return isMale ? '/LIA_TCM_BG.jpg' : '/LIA_TC_BG.jpg';
  }, [mounted, resolvedTheme, isMale]);

  return {
    isMale,
    mounted,
    liaImage: getLiaImage(),
    liaBackgroundImage: getLiaBackgroundImage(),
    toggleGender,
  };
}
