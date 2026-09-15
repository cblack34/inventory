import { describe, expect, it } from "vitest";
import { addDays } from "./dates";

describe("addDays", () => {
	it("adds days within a month", () => {
		expect(addDays("2026-01-01", 5)).toBe("2026-01-06");
	});

	it("carries over a month boundary", () => {
		expect(addDays("2026-01-30", 3)).toBe("2026-02-02");
	});

	it("carries over a year boundary", () => {
		expect(addDays("2025-12-30", 5)).toBe("2026-01-04");
	});

	it("handles a leap-year February", () => {
		expect(addDays("2024-02-28", 1)).toBe("2024-02-29");
	});

	it("accepts zero days as a no-op", () => {
		expect(addDays("2026-06-15", 0)).toBe("2026-06-15");
	});
});
