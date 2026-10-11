'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useTheme } from 'next-themes';

const LIA_GENDER_COOKIE = 'lia_gender';
const LIA_GENDER_CHANGE_EVENT = 'lia-gender-change';

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
    const syncGender = () => {
      const prefix = `${LIA_GENDER_COOKIE}=`;
      const genderCookie = document.cookie.split(';').find(c => c.trim().startsWith(prefix));
      setIsMale(genderCookie?.trim().slice(prefix.length) === 'male');
    };

    syncGender();
    // Cookie writes do not emit storage events. Notify mounted consumers in
    // this tab, and reread on focus for a choice made in another tab.
    window.addEventListener(LIA_GENDER_CHANGE_EVENT, syncGender);
    window.addEventListener('focus', syncGender);
    return () => {
      window.removeEventListener(LIA_GENDER_CHANGE_EVENT, syncGender);
      window.removeEventListener('focus', syncGender);
    };
  }, []);

  /**
   * Record a variant outright.
   *
   * The primitive, with `toggleGender` expressed on top of it: the hero picker
   * shows both portraits and the reader chooses one, which a flip cannot
   * express without the caller first comparing state — a read-then-write the
   * hook does correctly once, here.
   */
  const setGender = useCallback((male: boolean) => {
    setIsMale(male);
    // Save preference in cookie (1 year expiry)
    const expires = new Date();
    expires.setFullYear(expires.getFullYear() + 1);
    // SameSite=Lax blocks cross-site submission of the preference; Secure is
    // conditional on purpose — setting it unconditionally would make browsers
    // drop the cookie on a plain-HTTP dev origin, silently breaking the toggle.
    const secure = window.location.protocol === 'https:' ? '; Secure' : '';
    document.cookie = `${LIA_GENDER_COOKIE}=${male ? 'male' : 'female'}; expires=${expires.toUTCString()}; path=/; SameSite=Lax${secure}`;
    window.dispatchEvent(new Event(LIA_GENDER_CHANGE_EVENT));
  }, []);

  const toggleGender = useCallback(() => setGender(!isMale), [isMale, setGender]);

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

  /**
   * Both portraits for the CURRENT theme, so the picker can show the choice
   * rather than describe it.
   *
   * Theme-aware on purpose: offering the light-mode face while the hero
   * renders the dark one would make the thumbnails misdescribe what a click
   * produces. Before mount the light pair is returned, matching the
   * placeholder `getLiaImage` already serves (no hydration mismatch).
   */
  const liaImageVariants = useMemo(() => {
    const isDark = mounted && resolvedTheme === 'dark';
    return isDark
      ? { female: '/LIA_TS.jpg', male: '/LIA_TSM.jpg' }
      : { female: '/LIA_TC.jpg', male: '/LIA_TCM.jpg' };
  }, [mounted, resolvedTheme]);

  return {
    isMale,
    mounted,
    liaImage: getLiaImage(),
    liaBackgroundImage: getLiaBackgroundImage(),
    liaImageVariants,
    setGender,
    toggleGender,
  };
}
