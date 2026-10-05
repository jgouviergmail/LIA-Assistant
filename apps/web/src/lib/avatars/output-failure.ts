const CODES = [
  'avatar_output_failed',
  'avatar_no_remote_sound',
  'avatar_clock_stalled',
  'avatar_drain_timeout',
  'avatar_output_unavailable',
  'avatar_pcm_backlog_full',
  'voice_pcm_backlog_full',
  'voice_pcm_send_failed',
  'voice_pcm_send_stalled',
  'avatar_capture_failed',
  'avatar_rtc_failed',
  'avatar_media_failed',
  'avatar_socket_failed',
  'avatar_socket_closed',
  'avatar_bad_answer',
  'avatar_provider_closed',
  'avatar_send_failed',
] as const;
export type AvatarOutputFailure = (typeof CODES)[number];
/** Never retain arbitrary browser/provider exception text (it can contain a signed URL). */
export function outputFailureCode(error: unknown): AvatarOutputFailure {
  return (
    CODES.find(code => error instanceof Error && error.message === code) ?? 'avatar_output_failed'
  );
}
