'use client';
import type { ComponentProps } from 'react';
import type { LucideIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';

export function WorldWidgetButton({
  icon: Icon,
  label,
  ...props
}: ComponentProps<typeof Button> & { icon: LucideIcon; label: string }) {
  return (
    <Button
      variant="ghost"
      size="icon"
      className="world-widget-button min-h-11 min-w-11"
      aria-label={label}
      title={label}
      {...props}
    >
      <span className="world-device-icon">
        <Icon aria-hidden="true" />
      </span>
      <span className="world-device-label">{label}</span>
    </Button>
  );
}
