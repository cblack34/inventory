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
 */
export function addDays(isoDate: string, days: number): string {
	const [year = 0, month = 1, day = 1] = isoDate.split("-").map(Number);
	const shifted = new Date(Date.UTC(year, month - 1, day + days));
	return shifted.toISOString().slice(0, 10);
}
