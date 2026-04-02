/**
 * Personality Selector Component
 *
 * Dropdown menu to switch between LLM personalities.
 * Syncs selection to database for persistent preference.
 */

'use client';

import { useTranslation } from 'react-i18next';
import { Sparkles } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { usePersonality } from '@/hooks/usePersonality';
import { logger } from '@/lib/logger';
/**
 * Personality Selector
 *
 * Displays current personality and allows switching between all active personalities.
 * Updates the user's preference in the database.
 */
export function PersonalitySelector() {
  const { t } = useTranslation();
  const { personalities, currentPersonality, loading, updating, updatePersonality } =
    usePersonality();

  const handlePersonalityChange = async (personalityId: string | null) => {
    if (personalityId === currentPersonality?.id) return;

    try {
      await updatePersonality(personalityId);
      logger.info('Personality updated via header selector', {
        component: 'PersonalitySelector',
        newPersonalityId: personalityId,
      });
    } catch (error) {
      logger.error('Failed to update personality', error as Error, {
        component: 'PersonalitySelector',
        newPersonalityId: personalityId,
      });
    }
  };

  // Show loading state
  if (loading) {
    return (
      <Button variant="ghost" size="sm" className="gap-2 h-11" disabled>
        <Sparkles className="h-4 w-4 animate-pulse" />
        <span className="hidden sm:inline">...</span>
      </Button>
    );
  }

  // Get display text
  const displayEmoji = currentPersonality?.emoji || '⚖️';
  const displayTitle = currentPersonality?.title || t('personality.default', 'Normal');

  return (
    <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="sm" className="gap-2 h-11" disabled={updating}>
            <span className="text-base">{displayEmoji}</span>
            <span className="hidden sm:inline">{displayTitle}</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-64">
          {personalities.map(personality => (
            <DropdownMenuItem
              key={personality.id}
              onClick={() => handlePersonalityChange(personality.id)}
              className={currentPersonality?.id === personality.id ? 'bg-accent' : ''}
            >
              <span className="mr-2 text-base">{personality.emoji}</span>
              <div className="flex-1">
                <div className="font-medium">{personality.title}</div>
                <div className="text-xs text-muted-foreground line-clamp-1">
                  {personality.description}
                </div>
              </div>
              {currentPersonality?.id === personality.id && (
                <span className="ml-2 text-xs text-muted-foreground">✓</span>
              )}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
  );
}
