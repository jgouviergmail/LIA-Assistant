/**
 * The skill library's API shapes (ADR-327) — exactly what `/skill-library/*` answers.
 *
 * A portal's words (a name, a source, a description) are a stranger's text:
 * they are drawn as React children, never as markup. The identities the API
 * acts on are the repository, the folder and the COMMIT a preview read — an
 * install sends them back, so what is installed is what was shown.
 */

/** An audit verdict, least to most severe; `unknown` is no verdict at all. */
export type LibraryRisk = 'safe' | 'low' | 'medium' | 'high' | 'critical' | 'unknown';

/** Why a previewed skill cannot be installed as it is. */
export type LibraryConflict = 'none' | 'installed' | 'name_taken';

/** Where an installed skill stands against its source. */
export type LibraryUpdateState = 'current' | 'available' | 'unknown';

/** One skill a portal listed. */
export interface LibrarySearchItem {
  registry_id: string;
  name: string;
  source: string;
  skill_id: string;
  installs: number;
  /** The GitHub repository; null when the portal names an origin LIA does not read. */
  repository: string | null;
  supported: boolean;
  installed: boolean;
}

export interface LibrarySearchResponse {
  portal: string;
  items: LibrarySearchItem[];
  query_max_chars: number;
}

export interface LibraryAudit {
  provider: string;
  risk: LibraryRisk;
  alerts: number;
}

export interface LibraryFile {
  path: string;
  size: number;
}

/** A skill read at one commit, before it is installed. */
export interface LibraryPreview {
  portal: string | null;
  registry_id: string | null;
  repository: string;
  ref: string;
  path: string;
  commit_sha: string;
  tree_sha: string;
  name: string;
  description: string;
  files: LibraryFile[];
  skipped: string[];
  has_scripts: boolean;
  /** Null when the audit service could not be read. */
  audits: LibraryAudit[] | null;
  /** The audit risk that refuses the install on this instance, if any. */
  blocked_by: LibraryRisk | null;
  conflict: LibraryConflict;
}

/** A repository holding several skills: the folders to choose from. */
export interface LibraryFolderChoice {
  repository: string;
  ref: string;
  commit_sha: string;
  folders: string[];
}

export interface LibraryPreviewAnswer {
  preview: LibraryPreview | null;
  choice: LibraryFolderChoice | null;
}

/** What `/skill-library/preview` is asked: a portal skill, or a pasted address. */
export interface LibraryPreviewQuery {
  repository?: string;
  address?: string;
  skill_id?: string;
  path?: string;
  ref?: string;
  portal?: string;
  registry_id?: string;
}

export interface LibraryInstallRequest {
  repository: string;
  path: string;
  ref: string;
  commit_sha: string;
  portal: string | null;
  registry_id: string | null;
  skill_id: string | null;
}

export interface LibraryInstallResponse {
  skill_id: string;
  name: string;
  commit_sha: string;
}

export interface LibraryInstalledItem {
  skill_id: string;
  name: string;
  portal: string | null;
  repository: string;
  path: string;
  ref: string;
  commit_sha: string;
  update: LibraryUpdateState;
}

export interface LibraryInstalledResponse {
  items: LibraryInstalledItem[];
}

export interface LibraryChanges {
  added: string[];
  removed: string[];
  modified: string[];
}

export interface LibraryUpdatePreview {
  preview: LibraryPreview;
  changes: LibraryChanges;
}

/** The install request a preview makes: the commit it read, never the branch. */
export function installRequestOf(
  preview: LibraryPreview,
  skillId: string | null
): LibraryInstallRequest {
  return {
    repository: preview.repository,
    path: preview.path,
    ref: preview.ref,
    commit_sha: preview.commit_sha,
    portal: preview.portal,
    registry_id: preview.registry_id,
    skill_id: skillId,
  };
}

/** A commit as the reader scans it: its first seven characters. */
export function shortSha(sha: string): string {
  return sha.slice(0, 7);
}
