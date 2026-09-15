import { describe, expect, it } from "vitest";
import { centsToDollarsInput, parseDollarsToCents } from "./dollars";

describe("parseDollarsToCents", () => {
	it("parses whole and fractional dollars without floating-point math", () => {
		expect(parseDollarsToCents("1.23")).toBe(123);
		expect(parseDollarsToCents("0")).toBe(0);
		expect(parseDollarsToCents("5")).toBe(500);
		expect(parseDollarsToCents("1.2")).toBe(120);
	});

	it("parses a value that would drift under float multiplication", () => {
		// 0.1 + 0.2 !== 0.3 in IEEE-754; string math must still land exactly.
		// 4.35 * 100 === 434.99999999999994 in IEEE-754, which naive rounding
		// could truncate to the wrong cent.
		expect(parseDollarsToCents("0.10")).toBe(10);
		expect(parseDollarsToCents("4.35")).toBe(435);
	});

	it("parses a negative amount", () => {
		expect(parseDollarsToCents("-1.50")).toBe(-150);
	});

	it("rejects a bare fraction, too many fraction digits, or non-numeric input", () => {
		expect(parseDollarsToCents(".5")).toBeNull();
		expect(parseDollarsToCents("1.234")).toBeNull();
		expect(parseDollarsToCents("abc")).toBeNull();
		expect(parseDollarsToCents("")).toBeNull();
	});

	it("rejects a value whose cents exceed Number's safe-integer range", () => {
		// 20-digit cents value; Number.parseInt would silently round it rather
		// than return the exact amount.
		expect(parseDollarsToCents("100000000000000000.00")).toBeNull();
	});

	it("rejects a value above the API's per-field bound of 10**9 cents", () => {
		expect(parseDollarsToCents("10000000.00")).toBe(1000000000);
		expect(parseDollarsToCents("10000000.01")).toBeNull();
	});
});

describe("centsToDollarsInput", () => {
	it("round-trips through parseDollarsToCents", () => {
		expect(centsToDollarsInput(123)).toBe("1.23");
		expect(centsToDollarsInput(5)).toBe("0.05");
		expect(centsToDollarsInput(-150)).toBe("-1.50");
		for (const cents of [0, 5, 123, 1000, -150]) {
			expect(parseDollarsToCents(centsToDollarsInput(cents))).toBe(cents);
		}
	});
});
