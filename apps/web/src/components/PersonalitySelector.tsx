/**
 * Personality Selector Component
 *
 * Dropdown menu to switch between LLM personalities.
 * Syncs selection to database for persistent preference.
 */

'use client';

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Sparkles } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { AnimatedEmoji } from '@/components/ui/animated-emoji';
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
  const { personalities, currentPersonality, loading, refreshing, updating, updatePersonality } =
    usePersonality();
  // Animated emoji policy: the current personality in the header is always
  // alive; menu items animate only while hovered/focused (one loop at a time,
  // assets fetched on demand).
  const [hoveredId, setHoveredId] = useState<string | null>(null);

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
      <Button
        variant="ghost"
        size="sm"
        className="gap-2 h-11 px-3 max-[380px]:gap-1 max-[380px]:h-9 max-[380px]:px-2"
        disabled
        aria-label={t('common.loading')}
      >
        <Sparkles className="h-4 w-4 animate-pulse" />
        <span className="hidden xl:inline">...</span>
      </Button>
    );
  }

  // Get display text
  const displayEmoji = currentPersonality?.emoji || '⚖️';
  const displayTitle = currentPersonality?.title || t('personality.default', 'Normal');

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="gap-2 h-11 px-3 max-[380px]:gap-1 max-[380px]:h-9 max-[380px]:px-2"
          disabled={updating}
          // A reload of the catalogue (an administrator saving a style) must
          // announce itself without taking the control away: swapping it for
          // the loading placeholder would blank the header mid-session.
          aria-busy={refreshing}
          // The visible title is hidden below `xl` (the header row cannot fit
          // it next to the nav), and an emoji is not an accessible name — so
          // the name is carried explicitly and states the current value.
          aria-label={t('personality.selector_label', { name: displayTitle })}
        >
          <AnimatedEmoji
            glyph={displayEmoji}
            animate
            imgClassName="w-5 h-5"
            spanClassName="text-base"
          />
          <span className="hidden xl:inline">{displayTitle}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        {personalities.map(personality => (
          <DropdownMenuItem
            key={personality.id}
            onClick={() => handlePersonalityChange(personality.id)}
            onMouseEnter={() => setHoveredId(personality.id)}
            onMouseLeave={() => setHoveredId(prev => (prev === personality.id ? null : prev))}
            onFocus={() => setHoveredId(personality.id)}
            onBlur={() => setHoveredId(prev => (prev === personality.id ? null : prev))}
            className={currentPersonality?.id === personality.id ? 'bg-accent' : ''}
          >
            <span className="mr-2 flex w-5 h-5 items-center justify-center">
              <AnimatedEmoji
                glyph={personality.emoji}
                animate={hoveredId === personality.id}
                imgClassName="w-5 h-5"
                spanClassName="text-base"
              />
            </span>
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
