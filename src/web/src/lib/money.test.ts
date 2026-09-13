import { describe, expect, it } from "vitest";
import { formatCents } from "./money";

describe("formatCents", () => {
	it("formats whole and fractional dollars", () => {
		expect(formatCents(123)).toBe("$1.23");
		expect(formatCents(5)).toBe("$0.05");
	});

	it("formats negative cents", () => {
		expect(formatCents(-150)).toBe("-$1.50");
	});
});
