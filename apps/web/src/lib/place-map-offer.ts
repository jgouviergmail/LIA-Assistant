import type { AppConfig } from '@/hooks/useAppConfig';

/** Point maps share the same configured offer and authenticated admission policy. */
export function placeMapOffer(
  config: AppConfig | null,
  owner: string | null,
  hasPoint: boolean,
  language: string
): string | null {
  const offer = config?.place_maps;
  if (!owner || !offer?.enabled || !hasPoint) return null;
  const price = Number(offer.estimated_cost_eur);
  if (!Number.isFinite(price) || price <= 0) return null;
  return new Intl.NumberFormat(language, {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 5,
  }).format(price);
}
