/** Resolve an explicit civil midnight in the account zone, never the device zone.
 * The earliest instant wins on a repeated midnight. A skipped midnight refuses
 * rather than silently expanding a destructive date scope to another day.
 */
export function civilDateInstant(day: string, timeZone: string): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) throw new RangeError('Invalid civil date');
  const midnight = new Date(`${day}T00:00:00.000Z`);
  if (!Number.isFinite(midnight.getTime()) || midnight.toISOString().slice(0, 10) !== day)
    throw new RangeError('Invalid civil date');
  const target = midnight.getTime();
  const format = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  });
  const wallTime = (instant: number) => {
    const parts = format.formatToParts(new Date(instant));
    const get = (type: Intl.DateTimeFormatPartTypes) => {
      const value = parts.find(part => part.type === type)?.value;
      if (!value) throw new RangeError('Unrepresentable civil date');
      return value;
    };
    return Date.parse(
      `${get('year').padStart(4, '0')}-${get('month')}-${get('day')}T${get('hour')}:${get('minute')}:${get('second')}.000Z`
    );
  };
  const offsets = new Set(
    [-36, -24, -12, 0, 12, 24, 36].map(hours => {
      const sample = target + hours * 3_600_000;
      return wallTime(sample) - sample;
    })
  );
  const candidates = [...offsets]
    .map(offset => target - offset)
    .filter(instant => wallTime(instant) === target);
  if (!candidates.length) throw new RangeError('Civil midnight does not exist');
  return new Date(Math.min(...candidates)).toISOString();
}
