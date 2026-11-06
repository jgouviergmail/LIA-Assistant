'use client';

/**
 * The account's wall clock, to the minute (ADR-369, lot 2): the line of « now »
 * on the calendar. One timer, set to the next minute's turn so the line moves
 * when a clock would, and closed with its screen.
 */
import { useEffect, useState } from 'react';

import { instantToWall, type WallTime } from '@/lib/workbench/calendar/zoned';

const MINUTE_MS = 60_000;

/** @param zone - The account's zone. */
export function useWallClock(zone: string): WallTime {
  const [instant, setInstant] = useState(() => new Date());
  useEffect(() => {
    let timer = 0;
    const schedule = () => {
      timer = window.setTimeout(
        () => {
          setInstant(new Date());
          schedule();
        },
        MINUTE_MS - (Date.now() % MINUTE_MS)
      );
    };
    schedule();
    return () => window.clearTimeout(timer);
  }, []);
  return instantToWall(instant, zone);
}
