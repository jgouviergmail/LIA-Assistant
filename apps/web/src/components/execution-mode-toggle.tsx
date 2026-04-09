'use client';

import { useState, useEffect } from 'react';
import { Workflow, Zap } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { useAuth } from '@/hooks/useAuth';
import apiClient from '@/lib/api-client';
import { toast } from 'sonner';
import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';

interface ExecutionModeToggleProps {
  lng?: Language;
}

export function ExecutionModeToggle({ lng = 'fr' }: ExecutionModeToggleProps) {
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

    const newMode = user.execution_mode === 'react' ? 'pipeline' : 'react';
    setIsLoading(true);

    try {
      await apiClient.patch('/auth/me/execution-mode-preference', {
        execution_mode: newMode,
      });

      await refreshUser();

      toast.success(
        newMode === 'react' ? t('executionMode.toggle.enabled') : t('executionMode.toggle.disabled')
      );
    } catch (error) {
      console.error('Failed to update execution mode:', error);
      toast.error(t('common.error'));
    } finally {
      setIsLoading(false);
    }
  };

  // Show placeholder during SSR
  if (!mounted) {
    return (
      <Button variant="ghost" size="sm" className="w-11 h-11 px-0">
        <Workflow className="h-[1.2rem] w-[1.2rem]" />
        <span className="sr-only">{t('executionMode.toggle.enable_react')}</span>
      </Button>
    );
  }

  const isReact = user?.execution_mode === 'react';

  return (
    <Button
      variant="ghost"
      size="sm"
      className="w-11 h-11 px-0"
      onClick={handleToggle}
      disabled={isLoading || !user}
      aria-label={
        isReact ? t('executionMode.toggle.enable_pipeline') : t('executionMode.toggle.enable_react')
      }
      title={
        isReact
          ? t('executionMode.toggle.tooltip_react')
          : t('executionMode.toggle.tooltip_pipeline')
      }
    >
      {isLoading ? (
        <LoadingSpinner className="h-[1.2rem] w-[1.2rem]" />
      ) : isReact ? (
        <Zap className="h-[1.2rem] w-[1.2rem] text-amber-500 transition-all" />
      ) : (
        <Workflow className="h-[1.2rem] w-[1.2rem] text-muted-foreground transition-all" />
      )}
      <span className="sr-only">
        {isReact
          ? t('executionMode.toggle.enable_pipeline')
          : t('executionMode.toggle.enable_react')}
      </span>
    </Button>
  );
}
