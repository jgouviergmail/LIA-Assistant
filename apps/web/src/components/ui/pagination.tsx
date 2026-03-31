import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

/** Available page sizes for the selector. */
const PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const;

/** Default page size when none specified. */
const DEFAULT_PAGE_SIZE = 20;

export type PaginationVariant = 'centered' | 'justified';

export interface PaginationProps {
  /**
   * Current active page (1-indexed)
   */
  currentPage: number;

  /**
   * Total number of pages
   */
  totalPages: number;

  /**
   * Callback when page changes
   */
  onPageChange: (page: number) => void;

  /**
   * Layout variant
   * - 'centered': Buttons centered with page info in middle
   * - 'justified': Page info left, buttons right
   * @default 'justified'
   */
  variant?: PaginationVariant;

  /**
   * Total number of items (displayed in page info)
   */
  totalItems?: number;

  /**
   * Current page size (enables page size selector when provided with onPageSizeChange)
   */
  pageSize?: number;

  /**
   * Callback when page size changes
   */
  onPageSizeChange?: (size: number) => void;

  /**
   * Whether the table is currently loading (dims the controls)
   */
  loading?: boolean;

  /**
   * Labels for buttons and text (i18n support)
   */
  labels?: {
    previous?: string;
    next?: string;
    pageInfo?: (current: number, total: number) => string;
    itemsPerPage?: string;
    totalItems?: (count: number) => string;
  };

  /**
   * Additional className
   */
  className?: string;
}

/**
 * Pagination component with accessibility support and optional page size selector.
 *
 * Features:
 * - Two layout variants (centered/justified)
 * - Page size selector (10/20/50/100)
 * - Total items display
 * - Keyboard navigation (Tab, Enter)
 * - ARIA navigation landmark
 * - Disabled states for first/last pages
 * - Customizable labels for i18n
 */
export function Pagination({
  currentPage,
  totalPages,
  onPageChange,
  variant = 'justified',
  totalItems,
  pageSize,
  onPageSizeChange,
  loading = false,
  labels = {},
  className,
}: PaginationProps) {
  const {
    previous = 'Précédent',
    next = 'Suivant',
    pageInfo = (current, total) => `Page ${current} / ${total}`,
    itemsPerPage = 'par page',
    totalItems: totalItemsLabel = (count) => `(${count} résultats)`,
  } = labels;

  const handlePrevious = () => {
    if (currentPage > 1) {
      onPageChange(currentPage - 1);
    }
  };

  const handleNext = () => {
    if (currentPage < totalPages) {
      onPageChange(currentPage + 1);
    }
  };

  // Keyboard support
  const handleKeyDown = (e: React.KeyboardEvent, action: 'prev' | 'next') => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      if (action === 'prev') {
        handlePrevious();
      } else {
        handleNext();
      }
    }
  };

  if (totalPages <= 1 && !onPageSizeChange) {
    return null;
  }

  // Page size selector element (reused across variants)
  const pageSizeSelector = onPageSizeChange ? (
    <div className="flex items-center gap-1.5">
      <select
        value={pageSize ?? DEFAULT_PAGE_SIZE}
        onChange={e => {
          onPageSizeChange(Number(e.target.value));
          onPageChange(1);
        }}
        disabled={loading}
        className="h-8 rounded-md border border-input bg-background px-2 py-1 text-xs ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
        aria-label={itemsPerPage}
      >
        {PAGE_SIZE_OPTIONS.map(size => (
          <option key={size} value={size}>
            {size}
          </option>
        ))}
      </select>
      <span className="text-xs text-muted-foreground">{itemsPerPage}</span>
    </div>
  ) : null;

  // Page info text
  const pageInfoText = (
    <span aria-live="polite" aria-atomic="true">
      {pageInfo(currentPage, totalPages)}
      {totalItems !== undefined && (
        <span className="ml-1">{totalItemsLabel(totalItems)}</span>
      )}
    </span>
  );

  // Navigation buttons
  const navButtons = (
    <div className="flex gap-1">
      <Button
        variant="outline"
        size="sm"
        onClick={handlePrevious}
        onKeyDown={e => handleKeyDown(e, 'prev')}
        disabled={currentPage === 1 || loading}
        aria-label={`${previous}, page ${currentPage - 1}`}
        aria-disabled={currentPage === 1}
      >
        {previous}
      </Button>
      <Button
        variant="outline"
        size="sm"
        onClick={handleNext}
        onKeyDown={e => handleKeyDown(e, 'next')}
        disabled={currentPage === totalPages || totalPages === 0 || loading}
        aria-label={`${next}, page ${currentPage + 1}`}
        aria-disabled={currentPage === totalPages}
      >
        {next}
      </Button>
    </div>
  );

  if (variant === 'centered') {
    return (
      <nav
        className={cn('flex flex-col gap-2', className)}
        aria-label="Pagination"
        role="navigation"
      >
        <div className="flex justify-center items-center gap-2">
          {navButtons}
        </div>
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          {pageSizeSelector ?? <span />}
          {pageInfoText}
        </div>
      </nav>
    );
  }

  // Default: justified variant
  return (
    <nav
      className={cn('flex items-center justify-between text-xs text-muted-foreground', className)}
      aria-label="Pagination"
      role="navigation"
    >
      <div className="flex items-center gap-3">
        {pageSizeSelector}
        {pageInfoText}
      </div>
      {navButtons}
    </nav>
  );
}
