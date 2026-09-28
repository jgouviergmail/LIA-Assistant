'use client';

/**
 * One page of a gallery (ADR-279).
 *
 * A card per file: what it is, when it was produced, when it goes, and the two
 * things a person came for — open it, or delete it.
 *
 * Four rules, each already paid for elsewhere in this app:
 *
 * - **The expiry is STATED.** A generated file used to vanish with nothing said;
 *   the deadline sits on the card, in the person's own locale, and turns red
 *   once it is close.
 * - **The card IS the door.** Clicking anywhere on it opens the file (owner
 *   request 2026-09-25: an « Open » button beside a clickable card said the
 *   same thing twice). ONE link — the title — stretches over the card through
 *   a pseudo-element, the workboard card's pattern; the checkbox and the
 *   actions are raised above it, so a click on them stays theirs. One link per
 *   card, not three: a screen reader listed every file three times.
 * - **A download is a navigation, so it is an `<a>`, never a button**, and the
 *   selection checkbox is a real checkbox — no nested interactive controls
 *   (audit F013).
 * - **An image shows itself.** A gallery of filenames is a list, not a gallery;
 *   the thumbnail IS the identification, described by the file's own title.
 *
 * A file may be KEPT past its deadline (ADR-319): the card then says so where
 * the deadline was, and its pin is a toggle (`aria-pressed`) whose name stays
 * « Keep <file> » in both states — the state is announced, not the label.
 */

import { Download, Pin, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Pagination } from '@/components/ui/pagination';
import { useConfirm } from '@/components/ui/use-confirm';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { documentTypeIcon } from '@/components/chat/document-card-icon';
import { apiImageProps, apiResourceUrl } from '@/lib/utils/api-resource-url';
import { formatDate, formatFileSize } from '@/lib/format';
import { refusalSentence } from '@/lib/api-error';
import { assetLabel, assetOpenHref, expiryTone, isKept } from '@/lib/generated-assets/display';
import type { GeneratedAsset } from '@/types/generated-assets';
import { EmailAssetButton, SharedByLine, ShareAssetButton } from './AssetShareControls';

export interface GeneratedAssetGridProps {
  lng: Language;
  items: GeneratedAsset[];
  selected: ReadonlySet<string>;
  onToggle: (id: string) => void;
  page: number;
  totalPages: number;
  onPage: (page: number) => void;
  onDeleted: () => void;
  /** Whether the account may keep files at all (its ceiling is above 0). */
  keepOffered: boolean;
  /** Keep a file past its deadline, or release a kept one. */
  onKeepToggle: (asset: GeneratedAsset) => void;
}

/** Where a file's deadline is stated — or, for a kept file, that it has none. */
function AssetLifetimeLine({ lng, asset }: { lng: Language; asset: GeneratedAsset }) {
  const { t } = useTranslation(lng);
  if (asset.expires_at === null) {
    return (
      <p className="flex items-center gap-1 text-xs text-primary">
        <Pin className="h-3 w-3 shrink-0 fill-current" aria-hidden="true" />
        {t('settings.generated_assets.kept_line')}
      </p>
    );
  }
  // The deadline is STATED: a file that vanishes with nothing said is the
  // defect this line exists for.
  return (
    <p className={`text-xs ${expiryTone(asset.expires_at)}`}>
      {t('settings.generated_assets.expires_at', {
        when: formatDate(asset.expires_at, lng, { dateStyle: 'medium', timeStyle: 'short' }),
      })}
    </p>
  );
}

/** The pin: keep a file past its deadline, or release it. */
function KeepToggle({
  lng,
  asset,
  label,
  onToggle,
}: {
  lng: Language;
  asset: GeneratedAsset;
  label: string;
  onToggle: (asset: GeneratedAsset) => void;
}) {
  const { t } = useTranslation(lng);
  const kept = isKept(asset);
  return (
    <Button
      variant="ghost"
      size="sm"
      aria-pressed={kept}
      aria-label={t('settings.generated_assets.keep', { name: label })}
      onClick={() => onToggle(asset)}
      className={kept ? 'text-primary' : undefined}
    >
      <Pin className={`h-3.5 w-3.5 ${kept ? 'fill-current' : ''}`} aria-hidden="true" />
    </Button>
  );
}

export function GeneratedAssetGrid({
  lng,
  items,
  selected,
  onToggle,
  page,
  totalPages,
  onPage,
  onDeleted,
  keepOffered,
  onKeepToggle,
}: GeneratedAssetGridProps) {
  const { t } = useTranslation(lng);
  const { confirm, confirmDialog } = useConfirm();
  const { mutate: remove } = useApiMutation<undefined, undefined>({
    method: 'DELETE',
    componentName: 'GeneratedAssetGrid',
  });

  const deleteOne = async (asset: GeneratedAsset) => {
    const ok = await confirm({
      title: t('settings.generated_assets.confirm_delete_one_title'),
      description: assetLabel(asset),
      confirmLabel: t('common.delete'),
      destructive: true,
    });
    if (!ok) return;
    try {
      await remove(`/generated-assets/${asset.id}`, undefined);
    } catch (error) {
      // The mutation REJECTS on failure (it never resolves to null): without
      // this catch a refused delete was an unhandled rejection and no toast.
      toast.error(refusalSentence(error, t('common.error')));
      return;
    }
    toast.success(t('settings.generated_assets.deleted', { count: 1 }));
    onDeleted();
  };

  return (
    <div className="space-y-3">
      {confirmDialog}
      {/* `grid-cols-1` is not decoration: without an explicit template the
          phone column is an IMPLICIT `auto` track, sized to the cards'
          min-content — a nowrap title made it 665 px on a 320 px screen,
          inside a section that clips, so the page itself never scrolled
          (measured 2026-09-11). `grid-cols-1` is `repeat(1, minmax(0, 1fr))`:
          the 0 minimum is what lets the track — and the card, whose automatic
          minimum only applies against an `auto` minimum — shrink to fit. */}
      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {items.map(asset => {
          const label = assetLabel(asset);
          const isImage = asset.mime_type.startsWith('image/');
          const TypeMark = documentTypeIcon(
            asset.original_filename.split('.').pop()?.toLowerCase() ?? ''
          );
          return (
            <li
              key={asset.id}
              data-testid="generated-asset-card"
              className="relative flex flex-col gap-2 rounded-xl border border-border bg-card p-3 shadow-sm transition-shadow hover:shadow-md"
            >
              <div className="flex items-start gap-2">
                <Checkbox
                  id={`ga-${asset.id}`}
                  checked={selected.has(asset.id)}
                  onChange={() => onToggle(asset.id)}
                  aria-label={t('settings.generated_assets.select', { name: label })}
                  // Raised above the card's stretched door.
                  className="relative z-10 mt-0.5 shrink-0"
                />
                {/* The card's ONE door: the title link, stretched over the whole
                    card by its `::after`, whose ring outlines the card when the
                    link has the keyboard focus. Two lines, not one: on a phone
                    the title IS the identification of a document, and a single
                    `truncate` line kept ~30 characters of a request that starts
                    with the words every request shares. `break-words` lets a
                    filename with no space wrap instead of being clipped. The
                    full text stays in `title`. */}
                <a
                  href={assetOpenHref(asset, lng)}
                  target="_blank"
                  rel="noopener"
                  title={label}
                  aria-label={t('settings.generated_assets.open', { name: label })}
                  className="line-clamp-2 min-w-0 flex-1 break-words text-sm font-medium hover:underline focus-visible:outline-none after:absolute after:inset-0 after:rounded-xl after:content-[''] focus-visible:after:ring-2 focus-visible:after:ring-ring"
                >
                  {label}
                </a>
              </div>

              {!isImage && (
                <div
                  data-testid="generated-asset-typemark"
                  // The MARK of its type, where an image shows its thumbnail
                  // (ADR-279). Drawn at the thumbnail's height so a page mixing
                  // families keeps one rhythm instead of going ragged.
                  className="flex h-36 w-full items-center justify-center rounded-lg border border-border/60 bg-muted/40"
                >
                  <TypeMark className="h-10 w-10 text-muted-foreground" aria-hidden="true" />
                </div>
              )}

              {isImage && (
                <div className="overflow-hidden rounded-lg border border-border/60">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    {...apiImageProps(`/api/v1/attachments/${asset.id}`)}
                    alt={label}
                    loading="lazy"
                    // WHOLE, never cropped: `object-cover` filled the tile by
                    // cutting what did not fit, and on a thumbnail whose only
                    // job is « is this the file I am looking for? » the cut
                    // part is the part that answers. `contain` keeps the source
                    // ratio and letterboxes on the card's own ground, so the
                    // grid stays uniform without lying about the image.
                    className="h-36 w-full bg-muted/40 object-contain"
                  />
                </div>
              )}

              <p className="text-xs text-muted-foreground">
                {formatFileSize(asset.file_size)} · {formatDate(asset.created_at, lng)}
              </p>
              <SharedByLine lng={lng} asset={asset} />
              <AssetLifetimeLine lng={lng} asset={asset} />

              {/* Raised above the card's stretched door: a click here stays an
                  action, never an « open ». */}
              <div className="relative z-10 mt-auto flex items-center justify-end gap-1 pt-1">
                {/* A kept file can always be released, even once keeping is off. */}
                {(keepOffered || isKept(asset)) && (
                  <KeepToggle lng={lng} asset={asset} label={label} onToggle={onKeepToggle} />
                )}
                <Button asChild variant="ghost" size="sm">
                  <a
                    href={apiResourceUrl(`/api/v1/attachments/${asset.id}`)}
                    download={asset.original_filename}
                    aria-label={t('settings.generated_assets.download', { name: label })}
                  >
                    <Download className="h-3.5 w-3.5" aria-hidden="true" />
                  </a>
                </Button>
                <ShareAssetButton lng={lng} asset={asset} label={label} />
                <EmailAssetButton asset={asset} label={label} />
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => void deleteOne(asset)}
                  aria-label={t('settings.generated_assets.delete', { name: label })}
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                </Button>
              </div>
            </li>
          );
        })}
      </ul>

      {/* The app's own control: a second pagination is a second place for
          the keyboard behaviour and the ARIA landmark to be got wrong. */}
      {totalPages > 1 && (
        <Pagination
          currentPage={page}
          totalPages={totalPages}
          onPageChange={onPage}
          variant="centered"
          labels={{
            previous: t('common.previous'),
            next: t('common.next'),
            pageInfo: (current, count) =>
              t('settings.generated_assets.page_info', { current, total: count }),
          }}
        />
      )}
    </div>
  );
}
