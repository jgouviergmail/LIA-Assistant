/**
 * Utility functions for optimistic list updates with proper snapshot/rollback support
 */

/**
 * Update a single item in a list by ID
 *
 * @param list - The list to update
 * @param id - The ID of the item to update
 * @param updates - Partial updates to apply
 * @returns A new list with the updated item
 */
export function updateListItem<T extends { id: string }>(
  list: T[],
  id: string,
  updates: Partial<T>
): T[] {
  return list.map(item => (item.id === id ? { ...item, ...updates } : item));
}

/**
 * Delete an item from a list by ID
 *
 * @param list - The list to update
 * @param id - The ID of the item to delete
 * @returns A new list without the deleted item
 */
export function deleteListItem<T extends { id: string }>(list: T[], id: string): T[] {
  return list.filter(item => item.id !== id);
}

/**
 * Add an item to the beginning of a list
 *
 * @param list - The list to update
 * @param item - The item to add
 * @returns A new list with the added item at the start
 */
export function prependListItem<T>(list: T[], item: T): T[] {
  return [item, ...list];
}
