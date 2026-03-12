import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

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
   * @default 'centered'
   */
  variant?: PaginationVariant;

  /**
   * Labels for buttons (i18n support)
   */
  labels?: {
    previous?: string;
    next?: string;
    pageInfo?: (current: number, total: number) => string;
  };

  /**
   * Additional className
   */
  className?: string;
}

/**
 * Pagination component with accessibility support
 *
 * Features:
 * - Two layout variants (centered/justified)
 * - Keyboard navigation (Tab, Enter)
 * - ARIA navigation landmark
 * - Disabled states for first/last pages
 * - Customizable labels for i18n
 *
 * @example
 * <Pagination
 *   currentPage={page}
 *   totalPages={10}
 *   onPageChange={setPage}
 *   variant="centered"
 * />
 */
export function Pagination({
  currentPage,
  totalPages,
  onPageChange,
  variant = 'centered',
  labels = {},
  className,
}: PaginationProps) {
  const {
    previous = 'Précédent',
    next = 'Suivant',
    pageInfo = (current, total) => `Page ${current} / ${total}`,
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

  // Keyboard support: Arrow keys
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

  if (totalPages <= 1) {
    return null;
  }

  if (variant === 'justified') {
    return (
      <nav
        className={cn('flex items-center justify-between', className)}
        aria-label="Pagination"
        role="navigation"
      >
        {/* Page info - Left */}
        <div className="text-sm text-gray-600" aria-live="polite" aria-atomic="true">
          {pageInfo(currentPage, totalPages)}
        </div>

        {/* Buttons - Right */}
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handlePrevious}
            onKeyDown={e => handleKeyDown(e, 'prev')}
            disabled={currentPage === 1}
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
            disabled={currentPage === totalPages}
            aria-label={`${next}, page ${currentPage + 1}`}
            aria-disabled={currentPage === totalPages}
          >
            {next}
          </Button>
        </div>
      </nav>
    );
  }

  // Default: centered variant
  return (
    <nav
      className={cn('flex justify-center gap-2', className)}
      aria-label="Pagination"
      role="navigation"
    >
      <Button
        variant="outline"
        size="sm"
        onClick={handlePrevious}
        onKeyDown={e => handleKeyDown(e, 'prev')}
        disabled={currentPage === 1}
        aria-label={`${previous}, page ${currentPage - 1}`}
        aria-disabled={currentPage === 1}
      >
        {previous}
      </Button>

      <span
        className="flex items-center px-4 py-2 text-sm text-gray-700"
        aria-live="polite"
        aria-atomic="true"
        aria-current="page"
      >
        {pageInfo(currentPage, totalPages)}
      </span>

      <Button
        variant="outline"
        size="sm"
        onClick={handleNext}
        onKeyDown={e => handleKeyDown(e, 'next')}
        disabled={currentPage === totalPages}
        aria-label={`${next}, page ${currentPage + 1}`}
        aria-disabled={currentPage === totalPages}
      >
        {next}
      </Button>
    </nav>
  );
}
