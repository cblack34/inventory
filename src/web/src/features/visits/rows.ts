import type { components } from "@/api/types";

type StandRowIn = components["schemas"]["StandRowIn"];
type MarketRowIn = components["schemas"]["MarketRowIn"];

/**
 * A count field's form value: a real non-negative integer once the user has
 * typed one, or `""` while the input is blank (used only for the market
 * form's priced `returned`, which has no prefill — see
 * `docs/data-model.md` "Visit settlement").
 */
export type CountInput = number | "";

/** `register(name, { setValueAs: countSetValueAs })`: keeps a blank input as `""` instead of `NaN`. */
export function countSetValueAs(raw: string): CountInput {
	return raw === "" ? "" : Number(raw);
}

/** A valid non-negative integer, or `undefined` for blank or invalid input. */
export function normalizeCount(value: CountInput): number | undefined {
	if (value === "") {
		return undefined;
	}
	return Number.isInteger(value) && value >= 0 ? value : undefined;
}

export type StandRowFormValues = {
	sizeId: number;
	counted: number;
	tossed: number;
	pulled: number;
};

export type AddedRowFormValues = {
	sizeId: number;
	added: number;
};

/**
 * Merges the stand-section rows (counted, tossed, pulled) with the
 * kitchen-section rows (added) into one `StandRowIn` per size id, as the
 * API requires when a size is on hand at both the stand and Kitchen. A size
 * present in only one section gets zeros for the other section's fields,
 * which is always valid: zero on-hand at the missing side means zero is the
 * only legal value there.
 */
export function buildStandRows(
	countedRows: StandRowFormValues[],
	addedRows: AddedRowFormValues[],
): StandRowIn[] {
	const bySize = new Map<number, StandRowIn>();

	for (const row of countedRows) {
		bySize.set(row.sizeId, {
			size_id: row.sizeId,
			counted: row.counted,
			tossed: row.tossed,
			pulled: row.pulled,
			added: 0,
		});
	}

	for (const row of addedRows) {
		const existing = bySize.get(row.sizeId);
		if (existing) {
			existing.added = row.added;
		} else {
			bySize.set(row.sizeId, {
				size_id: row.sizeId,
				counted: 0,
				tossed: 0,
				pulled: 0,
				added: row.added,
			});
		}
	}

	return [...bySize.values()];
}

export type MarketRowFormValues = {
	sizeId: number;
	taken: CountInput;
	returned: CountInput;
	tossed: CountInput;
};

/**
 * Builds the market payload rows, dropping every size whose `taken` is zero
 * or blank — "sizes with taken 0 are omitted from the payload" per the
 * issue's form rules. Call only after zod validation has confirmed every
 * row with `taken > 0` carries valid `returned`/`tossed` counts.
 */
export function buildMarketRows(rows: MarketRowFormValues[]): MarketRowIn[] {
	return rows.flatMap((row): MarketRowIn[] => {
		const taken = normalizeCount(row.taken) ?? 0;
		if (taken === 0) {
			return [];
		}
		return [
			{
				size_id: row.sizeId,
				taken,
				returned: normalizeCount(row.returned) ?? 0,
				tossed: normalizeCount(row.tossed) ?? 0,
			},
		];
	});
}
