'use client';

/**
 * One page of a gallery (ADR-279).
 *
 * A card per file: what it is, when it was produced, when it goes, and the two
 * things a person came for — open it, or delete it.
 *
 * Three rules, each already paid for elsewhere in this app:
 *
 * - **The expiry is STATED.** A generated file used to vanish with nothing said;
 *   the deadline sits on the card, in the person's own locale, and turns red
 *   once it is close.
 * - **A download is a navigation, so it is an `<a>`, never a button.** Both
 *   controls are anchors, and the selection checkbox is a real checkbox — no
 *   nested interactive controls (audit F013).
 * - **An image shows itself.** A gallery of filenames is a list, not a gallery;
 *   the thumbnail IS the identification, and its accessible name is the file's
 *   own title.
 */

import { Download, ExternalLink, Trash2 } from 'lucide-react';
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
import { assetLabel, assetOpenHref, expiryTone } from '@/lib/generated-assets/display';
import type { GeneratedAsset } from '@/types/generated-assets';

export interface GeneratedAssetGridProps {
  lng: Language;
  items: GeneratedAsset[];
  selected: ReadonlySet<string>;
  onToggle: (id: string) => void;
  page: number;
  totalPages: number;
  onPage: (page: number) => void;
  onDeleted: () => void;
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
    const done = await remove(`/generated-assets/${asset.id}`, undefined);
    if (done === null) {
      toast.error(t('common.error'));
      return;
    }
    toast.success(t('settings.generated_assets.deleted', { count: 1 }));
    onDeleted();
  };

  return (
    <div className="space-y-3">
      {confirmDialog}
      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {items.map(asset => {
          const label = assetLabel(asset);
          const isImage = asset.mime_type.startsWith('image/');
          const TypeMark = documentTypeIcon(
            asset.original_filename.split('.').pop()?.toLowerCase() ?? ''
          );
          const tone = expiryTone(asset.expires_at);
          return (
            <li
              key={asset.id}
              data-testid="generated-asset-card"
              className="flex flex-col gap-2 rounded-xl border border-border bg-card p-3 shadow-sm"
            >
              <div className="flex items-start gap-2">
                <Checkbox
                  id={`ga-${asset.id}`}
                  checked={selected.has(asset.id)}
                  onChange={() => onToggle(asset.id)}
                  aria-label={t('settings.generated_assets.select', { name: label })}
                  className="mt-0.5 shrink-0"
                />
                <span className="min-w-0 flex-1 truncate text-sm font-medium" title={label}>
                  {label}
                </span>
              </div>

              {!isImage && (
                <a
                  href={assetOpenHref(asset, lng)}
                  target="_blank"
                  rel="noopener"
                  data-testid="generated-asset-typemark"
                  // The MARK of its type, where an image shows its thumbnail
                  // (ADR-279). Drawn at the thumbnail's height so a page mixing
                  // families keeps one rhythm instead of going ragged.
                  className="flex h-36 w-full items-center justify-center rounded-lg border border-border/60 bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  aria-label={t('settings.generated_assets.open', { name: label })}
                >
                  <TypeMark className="h-10 w-10 text-muted-foreground" aria-hidden="true" />
                </a>
              )}

              {isImage && (
                <a
                  href={assetOpenHref(asset, lng)}
                  target="_blank"
                  rel="noopener"
                  className="block overflow-hidden rounded-lg border border-border/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  aria-label={t('settings.generated_assets.open', { name: label })}
                >
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
                </a>
              )}

              <p className="text-xs text-muted-foreground">
                {formatFileSize(asset.file_size)} · {formatDate(asset.created_at, lng)}
              </p>
              {/* The deadline is STATED: a file that vanishes with nothing said
                  is the defect this line exists for. */}
              <p className={`text-xs ${tone}`}>
                {t('settings.generated_assets.expires_at', {
                  when: formatDate(asset.expires_at, lng, {
                    dateStyle: 'medium',
                    timeStyle: 'short',
                  }),
                })}
              </p>

              <div className="mt-auto flex items-center gap-1 pt-1">
                <Button asChild variant="outline" size="sm" className="flex-1">
                  <a
                    href={assetOpenHref(asset, lng)}
                    target="_blank"
                    rel="noopener"
                    aria-label={t('settings.generated_assets.open', { name: label })}
                  >
                    <ExternalLink className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                    {t('settings.generated_assets.open_short')}
                  </a>
                </Button>
                <Button asChild variant="ghost" size="sm">
                  <a
                    href={apiResourceUrl(`/api/v1/attachments/${asset.id}`)}
                    download={asset.original_filename}
                    aria-label={t('settings.generated_assets.download', { name: label })}
                  >
                    <Download className="h-3.5 w-3.5" aria-hidden="true" />
                  </a>
                </Button>
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
