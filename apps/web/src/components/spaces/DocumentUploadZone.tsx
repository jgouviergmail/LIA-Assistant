'use client';

import { useCallback, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Upload, Loader2, X, CheckCircle, XCircle } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { DocumentUploadState } from '@/hooks/useSpaceDocuments';

interface DocumentUploadZoneProps {
  onUpload: (file: File) => Promise<{ success?: boolean; error?: string }>;
  uploads: DocumentUploadState[];
  onDismissUpload: (tempId: string) => void;
  maxFileSizeMB?: number;
}

const ALLOWED_EXTENSIONS = '.pdf,.txt,.md,.docx';
const ALLOWED_MIMES = [
  'text/plain',
  'text/markdown',
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
];

export function DocumentUploadZone({
  onUpload,
  uploads,
  onDismissUpload,
  maxFileSizeMB = 20,
}: DocumentUploadZoneProps) {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const dragCounterRef = useRef(0);

  const maxSizeBytes = maxFileSizeMB * 1024 * 1024;

  const handleFiles = useCallback(
    (files: FileList | File[]) => {
      Array.from(files).forEach((file) => {
        if (!ALLOWED_MIMES.includes(file.type) && !file.name.match(/\.(pdf|txt|md|docx)$/i)) {
          return;
        }
        if (file.size > maxSizeBytes) {
          toast.error(t('spaces.documents.file_too_large', { name: file.name, maxSize: maxFileSizeMB }));
          return;
        }
        onUpload(file);
      });
    },
    [onUpload, maxSizeBytes, maxFileSizeMB, t]
  );

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    dragCounterRef.current += 1;
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    dragCounterRef.current -= 1;
    if (dragCounterRef.current <= 0) {
      dragCounterRef.current = 0;
      setIsDragOver(false);
    }
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      dragCounterRef.current = 0;
      setIsDragOver(false);
      if (e.dataTransfer.files.length > 0) {
        handleFiles(e.dataTransfer.files);
      }
    },
    [handleFiles]
  );

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files && e.target.files.length > 0) {
        handleFiles(e.target.files);
        e.target.value = '';
      }
    },
    [handleFiles]
  );

  return (
    <div className="space-y-3">
      {/* Mobile: button only */}
      <Button
        variant="outline"
        className="w-full sm:hidden"
        onClick={() => fileInputRef.current?.click()}
      >
        <Upload className="h-4 w-4 mr-2" />
        {t('spaces.documents.upload_button')}
      </Button>

      {/* Desktop: drag-and-drop zone */}
      <div
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            fileInputRef.current?.click();
          }
        }}
        onDragEnter={handleDragEnter}
        onDragOver={(e) => e.preventDefault()}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={cn(
          'hidden sm:flex rounded-lg border-2 border-dashed p-8 text-center cursor-pointer transition-all',
          'hover:border-primary/50 hover:bg-accent/30',
          'flex-col items-center gap-2',
          isDragOver && 'ring-2 ring-primary ring-inset bg-primary/5 border-primary'
        )}
      >
        <Upload className="h-8 w-8 text-muted-foreground" />
        <p className="text-sm font-medium">{t('spaces.documents.upload_hint')}</p>
        <p className="text-xs text-muted-foreground">
          {t('spaces.documents.upload_formats', { maxSize: maxFileSizeMB })}
        </p>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept={ALLOWED_EXTENSIONS}
        className="hidden"
        onChange={handleFileChange}
      />

      {/* Upload progress list */}
      {uploads.length > 0 && (
        <div className="space-y-2">
          {uploads.map((upload) => (
            <div
              key={upload.tempId}
              className="flex items-center gap-3 rounded-lg border p-3 bg-card"
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{upload.filename}</p>
                {upload.status === 'uploading' && (
                  <div className="mt-1 h-1.5 w-full rounded-full bg-muted overflow-hidden">
                    <div
                      className="h-full bg-primary rounded-full transition-all duration-300"
                      style={{ width: `${upload.progress}%` }}
                    />
                  </div>
                )}
              </div>
              {upload.status === 'uploading' && (
                <Loader2 className="h-4 w-4 animate-spin text-primary shrink-0" />
              )}
              {upload.status === 'done' && (
                <CheckCircle className="h-4 w-4 text-green-600 shrink-0" />
              )}
              {upload.status === 'error' && (
                <div className="flex items-center gap-1 shrink-0">
                  <XCircle className="h-4 w-4 text-destructive" />
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6"
                    onClick={() => onDismissUpload(upload.tempId)}
                  >
                    <X className="h-3 w-3" />
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
