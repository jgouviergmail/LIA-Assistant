/**
 * TypeScript types — mirror of apps/api/src/domains/briefing/schemas.py.
 *
 * Keep these in sync when adjusting the backend Pydantic models.
 */

// =============================================================================
// Status
// =============================================================================

export type CardStatus = 'ok' | 'empty' | 'error' | 'not_configured';

// =============================================================================
// Per-section payloads
// =============================================================================

export interface DailyForecastItem {
  date_iso: string;
  temp_min_c: number;
  temp_max_c: number;
  condition_code: string;
  icon_emoji: string;
}

export interface WeatherData {
  temperature_c: number;
  temperature_min_c: number | null;
  temperature_max_c: number | null;
  condition_code: string;
  description: string;
  icon_emoji: string;
  location_city: string | null;
  /** Wind speed in km/h */
  wind_speed_kmh: number | null;
  /** Cardinal direction: N, NE, E, SE, S, SW, W, NW */
  wind_direction_cardinal: string | null;
  /** Next 3 h precipitation probability (0.0 – 1.0) */
  precipitation_probability: number | null;
  forecast_alert: string | null;
  /** 5-day daily forecast (today + next 4 days) */
  daily_forecast: DailyForecastItem[];
}

export interface AgendaEventItem {
  title: string;
  start_local: string;
  end_local: string | null;
  location: string | null;
}

export interface AgendaData {
  events: AgendaEventItem[];
}

export interface MailItem {
  sender_name: string | null;
  sender_email: string | null;
  subject: string;
  received_local: string;
}

export interface MailsData {
  items: MailItem[];
  total_unread_today: number;
}

export interface BirthdayItem {
  contact_name: string;
  /** ISO 8601 'YYYY-MM-DD' if year known, '--MM-DD' otherwise */
  date_iso: string;
  days_until: number;
  /** Age the contact will turn at the upcoming birthday (null if birth year unknown) */
  age_at_next: number | null;
}

export interface BirthdaysData {
  items: BirthdayItem[];
}

export interface ReminderItem {
  content: string;
  trigger_at_local: string;
}

export interface RemindersData {
  items: ReminderItem[];
}

export type HealthKind = 'steps' | 'heart_rate';

export interface HealthSummaryItem {
  kind: HealthKind;
  /** Today's value (SUM for steps, AVG for heart_rate). null if no samples today */
  value_today: number | null;
  /** Per-day average over the rolling window. null if window is empty */
  value_avg_window: number | null;
  unit: string;
  /** Length of the rolling window (typically 14) */
  window_days: number;
  /** Number of days in the window with at least one sample */
  days_with_data: number;
}

export interface HealthData {
  items: HealthSummaryItem[];
}

// =============================================================================
// Generic envelopes
// =============================================================================

export type SectionData =
  | WeatherData
  | AgendaData
  | MailsData
  | BirthdaysData
  | RemindersData
  | HealthData
  | null;

export interface CardSection<T extends SectionData = SectionData> {
  status: CardStatus;
  data: T | null;
  /** ISO 8601 datetime (UTC) */
  generated_at: string;
  error_code: string | null;
  error_message: string | null;
}

export interface LLMUsage {
  tokens_in: number;
  tokens_out: number;
  tokens_cache: number;
  /** Computed cost in EUR via the active pricing cache */
  cost_eur: number;
  model_name: string | null;
}

export interface TextSection {
  text: string;
  /** ISO 8601 datetime (UTC) */
  generated_at: string;
  /** Token + cost breakdown for this LLM call. null when fallback path was taken. */
  usage: LLMUsage | null;
}

export interface CardsBundle {
  weather: CardSection<WeatherData>;
  agenda: CardSection<AgendaData>;
  mails: CardSection<MailsData>;
  birthdays: CardSection<BirthdaysData>;
  reminders: CardSection<RemindersData>;
  health: CardSection<HealthData>;
}

export interface BriefingResponse {
  greeting: TextSection;
  synthesis: TextSection | null;
  cards: CardsBundle;
}

// =============================================================================
// Section identifiers and refresh request
// =============================================================================

export type BriefingSection =
  | 'weather'
  | 'agenda'
  | 'mails'
  | 'birthdays'
  | 'reminders'
  | 'health';

export type RefreshScope = BriefingSection | 'all';

export interface RefreshRequest {
  sections: RefreshScope[];
}

// =============================================================================
// Error code → CTA mapping (stable codes from backend constants.py)
// =============================================================================

export const ERROR_CODE_CONNECTOR_NOT_CONFIGURED = 'connector_not_configured';
export const ERROR_CODE_CONNECTOR_OAUTH_EXPIRED = 'connector_oauth_expired';
export const ERROR_CODE_CONNECTOR_NETWORK = 'connector_network';
export const ERROR_CODE_CONNECTOR_RATE_LIMIT = 'connector_rate_limit';
export const ERROR_CODE_INTERNAL = 'internal';
