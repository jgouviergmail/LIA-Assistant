import { useEffect, useState } from 'react';

/**
 * Hook that debounces a value with proper cleanup to prevent memory leaks
 *
 * @param value - The value to debounce
 * @param delay - The delay in milliseconds
 * @returns The debounced value
 *
 * @example
 * const [searchInput, setSearchInput] = useState('')
 * const debouncedSearch = useDebounce(searchInput, 300)
 *
 * useEffect(() => {
 *   // This will only run 300ms after the user stops typing
 *   fetchResults(debouncedSearch)
 * }, [debouncedSearch])
 */
export function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    // Set up the timeout to update debounced value after delay
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    // ✅ CLEANUP: Clear timeout if value changes or component unmounts
    // This prevents memory leaks and ensures correct behavior
    return () => {
      clearTimeout(handler);
    };
  }, [value, delay]); // ✅ Exhaustive dependencies

  return debouncedValue;
}
