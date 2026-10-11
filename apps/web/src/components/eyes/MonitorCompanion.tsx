'use client';

import { ExpressiveEyes, type ExpressiveEyesProps } from './ExpressiveEyes';
import { cn } from '@/lib/utils';
import { MONITOR_SCREEN } from './monitor-geometry';
import { avatarLayoutProfile } from './layout-profiles';

/** Original static monitor skin; its face retains the native rig. */
export function MonitorCompanion(props: ExpressiveEyesProps) {
  return (
    <ExpressiveEyes
      {...props}
      volumeCharacter="monitor"
      layoutProfile={avatarLayoutProfile('monitor', props.volumeVariant ?? 'male')}
      screenBounds={MONITOR_SCREEN}
      className={cn('lia-monitor', props.className)}
    />
  );
}
