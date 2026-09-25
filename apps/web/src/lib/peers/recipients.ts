/**
 * What every surface listing the person's connections says about them.
 *
 * The image share dialog and the answer's share menu both list the accepted
 * connections, and both must tell « still loading », « could not be read » and
 * « none yet » apart — an empty list read as "no connection" when the request
 * merely failed would be a false statement about the account. The words live in
 * `settings.peers.recipients`; where to make a connection is written once here.
 */

import type { TFunction } from 'i18next';

/** « Settings › Connections », the place a connection is made. */
export function connectionsSettingsPath(t: TFunction): string {
  return `${t('settings.title')} › ${t('settings.peers.title')}`;
}
