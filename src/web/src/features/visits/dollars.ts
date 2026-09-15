/**
 * Parses a dollars-and-cents string (e.g. "12", "12.3", "0.05") into integer
 * cents. Only digit and decimal-point arithmetic on strings is used — never
 * a float division or multiplication of a dollar amount — so this can never
 * introduce the drift non-negotiable 4 forbids. Returns `null` for anything
 * that is not a non-negative amount with at most two decimal places.
 */
export function parseDollarsToCents(input: string): number | null {
	const match = /^(\d+)(?:\.(\d{1,2}))?$/.exec(input.trim());
	if (!match) {
		return null;
	}

	const [, wholePart, fractionPart] = match;
	const dollars = Number(wholePart);
	const cents = Number((fractionPart ?? "").padEnd(2, "0"));
	return dollars * 100 + cents;
}
