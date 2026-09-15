import { describe, expect, it } from "vitest";
import { summarizeBatchStates } from "./batchStateCounts";

describe("summarizeBatchStates", () => {
	it("sums expiring-soon and expired quantities separately", () => {
		expect(
			summarizeBatchStates([
				{ batch_id: 1, expires: "2026-09-16", quantity: 3, state: "ok" },
				{
					batch_id: 2,
					expires: "2026-09-17",
					quantity: 2,
					state: "expiring_soon",
				},
				{
					batch_id: 3,
					expires: "2026-09-18",
					quantity: 4,
					state: "expiring_soon",
				},
				{ batch_id: 4, expires: "2026-09-01", quantity: 1, state: "expired" },
			]),
		).toEqual({ expiringSoon: 6, expired: 1 });
	});

	it("returns zeros when every batch is ok or the list is empty", () => {
		expect(summarizeBatchStates([])).toEqual({ expiringSoon: 0, expired: 0 });
		expect(
			summarizeBatchStates([
				{ batch_id: 1, expires: "2026-09-16", quantity: 5, state: "ok" },
			]),
		).toEqual({ expiringSoon: 0, expired: 0 });
	});
});
