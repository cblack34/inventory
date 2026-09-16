/**
 * Adds `days` to an ISO `YYYY-MM-DD` date string. Uses UTC date parts (never
 * the local timezone) so the result can't drift by a day depending on the
 * browser's offset from midnight UTC.
 *
 * Returns `null` when the shifted date falls outside JavaScript's
 * representable `Date` range (roughly +/-273,790 years from the epoch) —
 * `shelf_life_days` is only server-validated as non-negative, so an
 * unusually large value must not throw out of `toISOString()`.
 */
export function addDays(isoDate: string, days: number): string | null {
	const [year = 0, month = 1, day = 1] = isoDate.split("-").map(Number);
	// `setUTCFullYear` rather than `Date.UTC(year, ...)`: the latter maps
	// years 0-99 to 1900-1999, and `baked` is user-editable.
	const shifted = new Date(0);
	shifted.setUTCFullYear(year, month - 1, day + days);
	if (Number.isNaN(shifted.getTime())) {
		return null;
	}
	const iso = shifted.toISOString().slice(0, 10);
	// Past year 9999 `toISOString` switches to an extended-year form
	// (`+010246-...`), which is not a date the API or a date input accepts.
	return /^\d{4}-\d{2}-\d{2}$/.test(iso) ? iso : null;
}
