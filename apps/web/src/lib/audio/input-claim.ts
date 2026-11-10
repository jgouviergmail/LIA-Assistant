/** Only one one-shot recorder owns this tab's microphone. No account or audio is retained here. */
let holder: symbol | null = null;
export function claimVoiceInput(owner: symbol): boolean {
  if (holder !== null && holder !== owner) return false;
  holder = owner;
  return true;
}
export function releaseVoiceInput(owner: symbol): void {
  if (holder === owner) holder = null;
}
