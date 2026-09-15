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
});
