import type { components } from "@/api/types";

type BatchStockRead = components["schemas"]["BatchStockRead"];

export type BatchStateCounts = {
	expiringSoon: number;
	expired: number;
};

/**
 * Sums a size row's batch quantities into the two states the home screen
 * flags, ignoring "ok" batches. The only arithmetic this performs is adding
 * numbers the API already returned per batch; it derives no stock or money.
 */
export function summarizeBatchStates(
	batches: BatchStockRead[],
): BatchStateCounts {
	let expiringSoon = 0;
	let expired = 0;

	for (const batch of batches) {
		if (batch.state === "expiring_soon") {
			expiringSoon += batch.quantity;
		} else if (batch.state === "expired") {
			expired += batch.quantity;
		}
	}

	return { expiringSoon, expired };
}
