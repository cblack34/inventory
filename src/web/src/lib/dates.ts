/** Today's calendar date in the browser's local timezone, as `YYYY-MM-DD`. */
export function todayIsoDate(): string {
	const now = new Date();
	const year = now.getFullYear();
	const month = String(now.getMonth() + 1).padStart(2, "0");
	const day = String(now.getDate()).padStart(2, "0");
	return `${year}-${month}-${day}`;
}

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
	const shifted = new Date(Date.UTC(year, month - 1, day + days));
	if (Number.isNaN(shifted.getTime())) {
		return null;
	}
	return shifted.toISOString().slice(0, 10);
}
