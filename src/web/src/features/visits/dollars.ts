/** The API's shared upper bound for a money field; see `Cents` in `src/inventory/api/schemas/numbers.py`. */
const MAX_CENTS = 10 ** 9;

/**
 * Parses a dollars-and-cents string (e.g. "12", "12.3", "0.05") into integer
 * cents. The cents value is built by string concatenation and parsed with a
 * single integer parse — never a float multiplication or division of a
 * dollar amount — so this can never introduce the drift non-negotiable 4
 * forbids. Returns `null` for anything that is not a non-negative amount
 * with at most two decimal places, or that falls outside the safe-integer
 * range or the API's per-field bound.
 */
export function parseDollarsToCents(input: string): number | null {
	const match = /^(\d+)(?:\.(\d{1,2}))?$/.exec(input.trim());
	if (!match) {
		return null;
	}

	const [, wholePart, fractionPart] = match;
	const centsString = `${wholePart}${(fractionPart ?? "").padEnd(2, "0")}`;
	const cents = Number.parseInt(centsString, 10);
	if (!Number.isSafeInteger(cents) || cents > MAX_CENTS) {
		return null;
	}
	return cents;
}
