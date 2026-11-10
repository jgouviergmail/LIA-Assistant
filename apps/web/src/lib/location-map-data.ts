import { z } from '@/lib/zod';
import type { PlacePositionData } from './place-position-data';

const locationMap = z
  .object({
    version: z.literal(1),
    label: z.string().min(1).max(200),
    address: z.string().max(1000),
    position: z
      .object({
        lat: z.number().finite().min(-90).max(90),
        lng: z.number().finite().min(-180).max(180),
      })
      .strict(),
  })
  .strict();

export type LocationMapData = z.infer<typeof locationMap>;

/** An archived point cannot supply executable URLs, credentials or extra fields. */
export function parseLocationMap(wire: unknown): LocationMapData | null {
  if (typeof wire !== 'string' || wire.length > 16384) return null;
  try {
    const result = locationMap.safeParse(JSON.parse(wire));
    return result.success ? result.data : null;
  } catch {
    return null;
  }
}

/** Adapt one address to the shared map's presentation contract, not the registry. */
export function locationMapPresentation(data: LocationMapData): PlacePositionData {
  return {
    version: 2,
    omitted_count: 0,
    unlocated_count: 0,
    places: [
      {
        ref: 'address',
        label: data.label,
        url: `https://www.google.com/maps/search/?api=1&query=${data.position.lat},${data.position.lng}`,
        position: data.position,
      },
    ],
  };
}
