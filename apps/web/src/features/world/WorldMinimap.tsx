'use client';

import { Compass } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from '@/components/ui/dropdown-menu';
import { WORLD } from './definition';
import { ACCENTS } from './art/palette';
import { mapPoint } from './minimap-geometry';
import type { Point, WorldDefinition, WorldSnapshot } from './types';

interface Props {
  snapshot: WorldSnapshot;
  world?: WorldDefinition;
  label: string;
  directoryLabel?: string;
  placeLabel?: (id: import('./types').ZoneId) => string;
  onExplore(point: Point): void;
  onRecenter(): void;
}

export function WorldMinimap({
  world = WORLD,
  snapshot,
  label,
  placeLabel,
  directoryLabel,
  onExplore,
  onRecenter,
}: Props) {
  const span = world.width + world.height;
  return (
    <div className="world-map-group">
      <button
        type="button"
        aria-label={label}
        title={label}
        className="world-minimap border border-border bg-background/95 shadow-lg"
        style={{ aspectRatio: `${span + 8}/${span / 2 + 8}` }}
        onClick={event => {
          if (event.detail === 0) {
            onRecenter();
            return;
          }
          const bounds = event.currentTarget.getBoundingClientRect();
          onExplore(
            mapPoint(
              {
                x: (event.clientX - bounds.left) / bounds.width,
                y: (event.clientY - bounds.top) / bounds.height,
              },
              world
            )
          );
        }}
      >
        <svg
          viewBox={`0 0 ${world.width + world.height + 8} ${(world.width + world.height) / 2 + 8}`}
          preserveAspectRatio="none"
          aria-hidden="true"
          className="h-full w-full"
        >
          <rect width="100%" height="100%" fill="#27433f" />
          <g transform={`translate(${world.height + 4}, 4) matrix(1 .5 -1 .5 0 0)`}>
            <rect width={world.width} height={world.height} fill="#94aa83" />
            {world.grounds.map((patch, index) => (
              <rect
                key={index}
                x={patch.x}
                y={patch.y}
                width={patch.width}
                height={patch.height}
                fill={
                  patch.kind === 'water' ? '#79adba' : patch.kind === 'path' ? '#d7cfb5' : '#c7b69a'
                }
              />
            ))}
            {world.zones.map(zone => (
              <rect
                key={zone.id}
                x={zone.x + 0.8}
                y={zone.y + 0.8}
                width={zone.width - 1.6}
                height={zone.height - 1.6}
                rx="1"
                fill={ACCENTS[zone.tone]}
                opacity=".8"
              />
            ))}
            <circle
              cx={snapshot.bip.x}
              cy={snapshot.bip.y}
              r="1.5"
              fill="#e7f6f3"
              stroke="#397a87"
              strokeWidth=".7"
            />
            <circle
              cx={snapshot.player.x}
              cy={snapshot.player.y}
              r="1.8"
              fill="#fff8df"
              stroke="#484c76"
              strokeWidth="1"
            />
          </g>
        </svg>
      </button>
      {placeLabel && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" className="world-map-trigger" data-world-place-menu>
              <Compass className="world-map-directory-icon" aria-hidden="true" />
              <span>{directoryLabel ?? label}</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            className="world-map-directory"
            aria-label={directoryLabel ?? label}
            align="end"
            sideOffset={6}
          >
            {world.zones.map(zone => (
              <DropdownMenuItem
                key={zone.id}
                onSelect={() =>
                  onExplore({ x: zone.x + zone.width / 2, y: zone.y + zone.height / 2 })
                }
              >
                <span
                  aria-hidden="true"
                  className="world-place-color"
                  style={{ background: ACCENTS[zone.tone] }}
                />
                {placeLabel(zone.id)}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </div>
  );
}
