/** Compiled into the server catalogue: prediction and authority use the same speeds. */
export const MOVEMENT = Object.freeze({ walk: 3.4, run: 5.1 });
/** Client-only: a snapshot older than this no longer authorizes movement or an action. */
export const FRESH_SNAPSHOT_MS = 2000;
