'use client';

import { AlertTriangle, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

interface BriefingErrorProps {
  onRetry: () => void;
}

/**
 * Page-level fallback when the initial GET /briefing/today fails entirely
 * (network down, backend 5xx, etc.). The card-level errors are handled inside
 * <BriefingCard /> instead.
 */
export function BriefingError({ onRetry }: BriefingErrorProps) {
  const { t } = useTranslation();
  return (
    <Card variant="elevated" status="error" className="max-w-md mx-auto">
      <CardContent className="p-6 flex flex-col items-center text-center gap-4">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
          <AlertTriangle className="h-6 w-6 text-destructive" />
        </div>
        <div className="space-y-1">
          <h2 className="text-base font-semibold">
            {t('dashboard.briefing.errors.page_title')}
          </h2>
          <p className="text-sm text-muted-foreground">
            {t('dashboard.briefing.errors.page_description')}
          </p>
        </div>
        <Button variant="default" size="sm" onClick={onRetry}>
          <RefreshCw className="h-4 w-4" />
          {t('dashboard.briefing.errors.retry')}
        </Button>
      </CardContent>
    </Card>
  );
}
