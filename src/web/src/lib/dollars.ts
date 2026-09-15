/**
 * Parses a dollars string like "1.23" into integer cents using string math,
 * never float multiplication (non-negotiable 4: money is never a float).
 * Accepts an optional leading "-", one or more digits, and an optional
 * one- or two-digit fractional part. Returns `null` for anything else,
 * including a bare fraction like ".5" or a three-digit fraction.
 */
export function parseDollarsToCents(input: string): number | null {
	const match = /^(-?)(\d+)(?:\.(\d{1,2}))?$/.exec(input.trim());
	if (!match) {
		return null;
	}
	const [, sign, whole, fraction] = match;
	const centsDigits = (fraction ?? "").padEnd(2, "0");
	const magnitude = Number.parseInt(`${whole}${centsDigits}`, 10);
	return sign === "-" ? -magnitude : magnitude;
}

/** Inverse of `parseDollarsToCents`, for prefilling an editable dollars input. */
export function centsToDollarsInput(cents: number): string {
	const sign = cents < 0 ? "-" : "";
	const absCents = Math.abs(cents);
	const dollars = Math.trunc(absCents / 100);
	const remainder = absCents % 100;
	return `${sign}${dollars}.${remainder.toString().padStart(2, "0")}`;
}
