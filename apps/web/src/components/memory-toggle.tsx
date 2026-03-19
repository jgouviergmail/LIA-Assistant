'use client';

import { useState, useEffect } from 'react';
import { Brain, BrainCog } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { useAuth } from '@/hooks/useAuth';
import apiClient from '@/lib/api-client';
import { toast } from 'sonner';
import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';

interface MemoryToggleProps {
  lng?: Language;
}

export function MemoryToggle({ lng = 'fr' }: MemoryToggleProps) {
  const { user, refreshUser } = useAuth();
  const { t } = useTranslation(lng);
  const [mounted, setMounted] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  // Avoid hydration mismatch
  useEffect(() => {
    setMounted(true);
  }, []);

  const handleToggle = async () => {
    if (!user || isLoading) return;

    const newState = !user.memory_enabled;
    setIsLoading(true);

    try {
      await apiClient.patch('/auth/me/memory-preference', {
        memory_enabled: newState,
      });

      // Refresh user to get updated state
      await refreshUser();

      toast.success(newState ? t('memory.toggle.enabled') : t('memory.toggle.disabled'));
    } catch (error) {
      console.error('Failed to update memory preference:', error);
      toast.error(t('common.error'));
    } finally {
      setIsLoading(false);
    }
  };

  // Show placeholder during SSR
  if (!mounted) {
    return (
      <Button variant="ghost" size="sm" className="w-11 h-11 px-0">
        <Brain className="h-[1.2rem] w-[1.2rem]" />
        <span className="sr-only">{t('memory.toggle.enable')}</span>
      </Button>
    );
  }

  const isEnabled = user?.memory_enabled ?? true;

  return (
    <Button
      variant="ghost"
      size="sm"
      className="w-11 h-11 px-0"
      onClick={handleToggle}
      disabled={isLoading || !user}
      aria-label={isEnabled ? t('memory.toggle.disable') : t('memory.toggle.enable')}
      title={isEnabled ? t('memory.toggle.tooltip_enabled') : t('memory.toggle.tooltip_disabled')}
    >
      {isLoading ? (
        <LoadingSpinner className="h-[1.2rem] w-[1.2rem]" />
      ) : isEnabled ? (
        <Brain className="h-[1.2rem] w-[1.2rem] text-primary transition-all" />
      ) : (
        <BrainCog className="h-[1.2rem] w-[1.2rem] text-muted-foreground transition-all" />
      )}
      <span className="sr-only">
        {isEnabled ? t('memory.toggle.disable') : t('memory.toggle.enable')}
      </span>
    </Button>
  );
}
