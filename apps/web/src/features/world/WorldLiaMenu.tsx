'use client';
import { Bell, BookOpen, Brain, MessageCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { WorldSelection } from './activity-entry';

const CHOICES = [
  { id: 'conversation', selection: 'lia', Icon: MessageCircle },
  { id: 'journal', selection: 'journals', Icon: BookOpen },
  { id: 'alerts', selection: 'world-alerts', Icon: Bell },
  { id: 'psyche', selection: 'psyche', Icon: Brain },
] as const satisfies readonly { id: string; selection: WorldSelection; Icon: typeof Bell }[];
export function WorldLiaMenu({
  lng,
  onSelect,
}: {
  lng: Language;
  onSelect: (selection: WorldSelection) => void;
}) {
  const { t } = useTranslation(lng);
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {CHOICES.map(({ id, selection, Icon }) => (
        <Button
          key={id}
          variant="outline"
          className="min-h-20 justify-start gap-3 whitespace-normal text-left"
          onClick={() => onSelect(selection)}
        >
          <Icon className="size-6 shrink-0 text-primary" aria-hidden="true" />
          {t('world.lia_menu.' + id)}
        </Button>
      ))}
    </div>
  );
}
