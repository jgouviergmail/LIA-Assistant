import type { PhotoAuthor } from '@/lib/place-photos';
import { useTranslation } from 'react-i18next';
import { apiImageProps } from '@/lib/utils/api-resource-url';
import { proxyGoogleImageUrl } from '@/lib/utils';

export function PhotoAttribution({
  authors,
  sourceUrl,
}: {
  authors?: readonly PhotoAuthor[];
  sourceUrl?: string;
}) {
  const { t } = useTranslation();
  if (!authors) return null;
  return (
    <div className="lia-photo-attribution">
      <span className="lia-google-attribution" translate="no">
        Google Maps
      </span>
      {authors.map((author, index) => (
        <span key={`${author.name}-${index}`}>
          {' '}
          · <AuthorAvatar source={author.avatarUrl} />
          {author.url ? (
            <a href={author.url} target="_blank" rel="noopener noreferrer">
              {author.name}
            </a>
          ) : (
            <span>{author.name}</span>
          )}
        </span>
      ))}
      {sourceUrl && (
        <span>
          {' '}
          ·{' '}
          <a href={sourceUrl} target="_blank" rel="noopener noreferrer">
            {t('gallery.view_source')}
          </a>
        </span>
      )}
    </div>
  );
}

function AuthorAvatar({ source }: { source?: string }) {
  if (!source) return null;
  // Decorative: the adjacent author name already supplies the accessible text.
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      {...apiImageProps(proxyGoogleImageUrl(source) || source)}
      className="lia-photo-author__avatar"
      width={20}
      height={20}
      alt=""
      loading="lazy"
      referrerPolicy="no-referrer"
    />
  );
}
