import type { AppConfig } from '@/hooks/useAppConfig';

/** What the server takes as an upload, as it publishes it (`/config` → `attachments`). */
export interface AttachmentFormats {
  /** The image MIME types the instance allows. */
  image_types: string[];
  /** The document file extensions the instance allows, each with its dot. */
  document_extensions: string[];
}

/**
 * What a server that publishes nothing takes: the historical images and PDFs.
 * The upload itself still decides — this only keeps the composer offering
 * what it always offered in front of an older API.
 */
export const DEFAULT_ATTACHMENT_FORMATS: AttachmentFormats = {
  image_types: [],
  document_extensions: ['.pdf'],
};

/**
 * The formats the composer may offer, from the instance's own allowlists.
 *
 * @param config - The app configuration, or `null` while it loads.
 * @returns What the instance publishes, or the historical default.
 */
export function attachmentFormats(config: AppConfig | null): AttachmentFormats {
  return config?.attachments ?? DEFAULT_ATTACHMENT_FORMATS;
}

/**
 * The `accept` of the file picker: every image, and the documents by NAME.
 *
 * Extensions rather than MIME types: a browser reports no type for a `.md`
 * and a spreadsheet's type for a `.csv`, so a MIME filter would grey out
 * files the server takes.
 */
export function pickerAccept(formats: AttachmentFormats = DEFAULT_ATTACHMENT_FORMATS): string {
  return ['image/*', ...formats.document_extensions].join(',');
}

/** The extension of a file name, lower-cased, with its dot; `''` when it has none. */
function extensionOf(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot > 0 ? name.slice(dot).toLowerCase() : '';
}

/**
 * Whether the composer takes a file: a picture by its type, a document by its
 * name. The ONE reading of the published formats — the drop, the paste and the
 * upload door all ask it, so none of them refuses what another offered.
 *
 * It never promises more than a name can: the server decides on the content,
 * and refuses what the name misdescribed.
 */
export function isAcceptedFile(
  file: File,
  formats: AttachmentFormats = DEFAULT_ATTACHMENT_FORMATS
): boolean {
  return (
    file.type.startsWith('image/') || formats.document_extensions.includes(extensionOf(file.name))
  );
}

/** The files of a drop or a paste the composer keeps (see {@link isAcceptedFile}). */
export function acceptedFiles(
  list: ArrayLike<File>,
  formats: AttachmentFormats = DEFAULT_ATTACHMENT_FORMATS
): File[] {
  return Array.from(list).filter(file => isAcceptedFile(file, formats));
}
