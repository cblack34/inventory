import { describe, expect, it } from "vitest";
import { parseDollarsToCents } from "./dollars";

describe("parseDollarsToCents", () => {
	it("parses a whole dollar amount", () => {
		expect(parseDollarsToCents("12")).toBe(1200);
	});

	it("parses one and two decimal places", () => {
		expect(parseDollarsToCents("12.3")).toBe(1230);
		expect(parseDollarsToCents("12.34")).toBe(1234);
	});

	it("parses zero", () => {
		expect(parseDollarsToCents("0")).toBe(0);
		expect(parseDollarsToCents("0.00")).toBe(0);
	});

	it("trims surrounding whitespace", () => {
		expect(parseDollarsToCents("  5.50  ")).toBe(550);
	});

	it("rejects a negative amount", () => {
		expect(parseDollarsToCents("-1")).toBeNull();
	});

	it("rejects more than two decimal places", () => {
		expect(parseDollarsToCents("1.234")).toBeNull();
	});

	it("rejects non-numeric input", () => {
		expect(parseDollarsToCents("")).toBeNull();
		expect(parseDollarsToCents("abc")).toBeNull();
	});

	it("accepts an amount at the API's per-field bound", () => {
		expect(parseDollarsToCents("10000000.00")).toBe(1_000_000_000);
	});

	it("rejects an amount over the API's per-field bound", () => {
		expect(parseDollarsToCents("10000000.01")).toBeNull();
	});

	it("rejects a huge amount without losing precision to a float path", () => {
		// Far beyond Number.MAX_SAFE_INTEGER cents; must be rejected outright
		// rather than silently rounded to some other in-range value.
		expect(parseDollarsToCents("99999999999999999999.99")).toBeNull();
	});
});
