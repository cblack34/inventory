/** Formats integer cents as a dollar string, e.g. 123 -> "$1.23". */
export function formatCents(cents: number): string {
	const sign = cents < 0 ? "-" : "";
	const absCents = Math.abs(cents);
	const dollars = Math.trunc(absCents / 100);
	const remainder = absCents % 100;
	return `${sign}$${dollars}.${remainder.toString().padStart(2, "0")}`;
}
