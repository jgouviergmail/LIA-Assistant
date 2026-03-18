/**
 * Tests for DocumentUploadZone component.
 *
 * Covers: file type validation, file size validation, upload progress
 * rendering, and error state with dismiss button.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DocumentUploadZone } from '../DocumentUploadZone';
import type { DocumentUploadState } from '@/hooks/useSpaceDocuments';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockToastError = vi.fn();

vi.mock('sonner', () => ({
  toast: {
    error: (...args: unknown[]) => mockToastError(...args),
    success: vi.fn(),
    info: vi.fn(),
  },
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createFile(name: string, size: number, type: string): File {
  const buffer = new ArrayBuffer(size);
  return new File([buffer], name, { type });
}

const defaultProps = {
  onUpload: vi.fn().mockResolvedValue({ success: true }),
  uploads: [] as DocumentUploadState[],
  onDismissUpload: vi.fn(),
  maxFileSizeMB: 20,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('DocumentUploadZone', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('accepts valid file types', () => {
    const onUpload = vi.fn().mockResolvedValue({ success: true });
    render(<DocumentUploadZone {...defaultProps} onUpload={onUpload} />);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    expect(input).toBeTruthy();

    const pdfFile = createFile('doc.pdf', 1024, 'application/pdf');
    fireEvent.change(input, { target: { files: [pdfFile] } });

    expect(onUpload).toHaveBeenCalledWith(pdfFile);
    expect(mockToastError).not.toHaveBeenCalled();
  });

  it('rejects files with unsupported types', () => {
    const onUpload = vi.fn().mockResolvedValue({ success: true });
    render(<DocumentUploadZone {...defaultProps} onUpload={onUpload} />);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const exeFile = createFile('malware.exe', 1024, 'application/x-msdownload');
    fireEvent.change(input, { target: { files: [exeFile] } });

    expect(onUpload).not.toHaveBeenCalled();
  });

  it('shows toast error when file exceeds max size', () => {
    const onUpload = vi.fn().mockResolvedValue({ success: true });
    const maxFileSizeMB = 5;
    render(
      <DocumentUploadZone
        {...defaultProps}
        onUpload={onUpload}
        maxFileSizeMB={maxFileSizeMB}
      />
    );

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    // 6 MB file exceeds the 5 MB limit
    const largeFile = createFile('huge.pdf', 6 * 1024 * 1024, 'application/pdf');
    fireEvent.change(input, { target: { files: [largeFile] } });

    expect(onUpload).not.toHaveBeenCalled();
    // t() mock returns the key, so toast.error receives just the i18n key
    expect(mockToastError).toHaveBeenCalledWith(
      'spaces.documents.file_too_large'
    );
  });

  it('renders upload progress for active uploads', () => {
    const uploads: DocumentUploadState[] = [
      { tempId: 'tmp-1', filename: 'report.pdf', progress: 45, status: 'uploading' },
      { tempId: 'tmp-2', filename: 'notes.txt', progress: 100, status: 'done' },
    ];

    render(<DocumentUploadZone {...defaultProps} uploads={uploads} />);

    expect(screen.getByText('report.pdf')).toBeInTheDocument();
    expect(screen.getByText('notes.txt')).toBeInTheDocument();
  });

  it('renders error state with dismiss button that calls onDismissUpload', () => {
    const onDismissUpload = vi.fn();
    const uploads: DocumentUploadState[] = [
      {
        tempId: 'tmp-err',
        filename: 'broken.docx',
        progress: 0,
        status: 'error',
        error: 'Upload failed',
      },
    ];

    render(
      <DocumentUploadZone
        {...defaultProps}
        uploads={uploads}
        onDismissUpload={onDismissUpload}
      />
    );

    expect(screen.getByText('broken.docx')).toBeInTheDocument();

    // The dismiss button is a ghost icon button inside the error state
    const dismissButtons = screen.getAllByRole('button');
    // Find the small dismiss button (the X icon button, not the main upload button)
    const dismissBtn = dismissButtons.find(
      (btn) => btn.classList.contains('h-6') && btn.classList.contains('w-6')
    );
    expect(dismissBtn).toBeTruthy();

    fireEvent.click(dismissBtn!);
    expect(onDismissUpload).toHaveBeenCalledWith('tmp-err');
  });

  it('handles file input accept attribute correctly', () => {
    render(<DocumentUploadZone {...defaultProps} />);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    expect(input.accept).toBe('.pdf,.txt,.md,.docx,.pptx,.xlsx,.csv,.rtf,.html,.htm,.odt,.ods,.odp,.epub,.json,.xml');
    expect(input.multiple).toBe(true);
  });
});
