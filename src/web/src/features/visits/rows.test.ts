import { describe, expect, it } from "vitest";
import {
	buildMarketRows,
	buildStandRows,
	countSetValueAs,
	normalizeCount,
} from "./rows";

describe("normalizeCount", () => {
	it("returns undefined for a blank input", () => {
		expect(normalizeCount("")).toBeUndefined();
	});

	it("returns the integer for a valid input", () => {
		expect(normalizeCount(0)).toBe(0);
		expect(normalizeCount(5)).toBe(5);
	});

	it("rejects a negative or non-integer number", () => {
		expect(normalizeCount(-1)).toBeUndefined();
		expect(normalizeCount(1.5)).toBeUndefined();
		expect(normalizeCount(Number.NaN)).toBeUndefined();
	});
});

describe("countSetValueAs", () => {
	it("keeps a blank input as an empty string", () => {
		expect(countSetValueAs("")).toBe("");
	});

	it("converts a filled input to a number", () => {
		expect(countSetValueAs("3")).toBe(3);
	});
});

describe("buildStandRows", () => {
	it("merges a size present in both sections into one row", () => {
		const rows = buildStandRows(
			[{ sizeId: 1, counted: 4, tossed: 1, pulled: 0 }],
			[{ sizeId: 1, added: 2 }],
		);
		expect(rows).toEqual([
			{ size_id: 1, counted: 4, tossed: 1, pulled: 0, added: 2 },
		]);
	});

	it("zero-fills the added field for a stand-only size", () => {
		const rows = buildStandRows(
			[{ sizeId: 1, counted: 4, tossed: 0, pulled: 0 }],
			[],
		);
		expect(rows).toEqual([
			{ size_id: 1, counted: 4, tossed: 0, pulled: 0, added: 0 },
		]);
	});

	it("zero-fills counted/tossed/pulled for a kitchen-only size", () => {
		const rows = buildStandRows([], [{ sizeId: 2, added: 3 }]);
		expect(rows).toEqual([
			{ size_id: 2, counted: 0, tossed: 0, pulled: 0, added: 3 },
		]);
	});
});

describe("buildMarketRows", () => {
	it("drops a size whose taken is zero", () => {
		const rows = buildMarketRows([
			{ sizeId: 1, taken: 0, returned: "", tossed: 0 },
			{ sizeId: 2, taken: 5, returned: 4, tossed: 1 },
		]);
		expect(rows).toEqual([{ size_id: 2, taken: 5, returned: 4, tossed: 1 }]);
	});

	it("drops a size whose taken is blank", () => {
		const rows = buildMarketRows([
			{ sizeId: 1, taken: "", returned: "", tossed: "" },
		]);
		expect(rows).toEqual([]);
	});
});
