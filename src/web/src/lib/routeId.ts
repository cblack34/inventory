/**
 * Parses a route param (e.g. `:recipeId`, `:entryId`) as a positive safe
 * integer id, or `null` if it is missing or malformed. Requires the entire
 * string to be decimal digits before parsing — `Number.parseInt` alone
 * would accept `"1.5"` or `"1abc"` as `1`, and a bare `Number()` would
 * accept `"-1"`, `"1e3"`, and unsafe integers like `9007199254740993`
 * (silently rounded before use) — any of which could route to the wrong
 * record for a malformed URL.
 */
export function parseRouteId(param: string | undefined): number | null {
	if (!param || !/^\d+$/.test(param)) {
		return null;
	}
	const id = Number(param);
	return Number.isSafeInteger(id) && id > 0 ? id : null;
}
