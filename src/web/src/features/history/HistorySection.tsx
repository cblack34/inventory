import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { request } from "@/api/client";
import type { components } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCents } from "@/lib/money";
import { problemMessage } from "@/lib/problemMessage";

type EntryRead = components["schemas"]["EntryRead"];
type LocationRead = components["schemas"]["LocationRead"];
type ReversalCreate = components["schemas"]["ReversalCreate"];
type ReversalRead = components["schemas"]["ReversalRead"];

/**
 * History newest first, exactly as the API returns it (`GET /entries` is
 * already ordered; this component never re-sorts). Location names come from
 * `GET /locations` since entries carry only a `location_id`.
 */
export function HistorySection() {
	const entriesQuery = useQuery({
		queryKey: ["entries"],
		queryFn: () => request<EntryRead[]>("GET", "/api/v1/entries"),
	});
	const locationsQuery = useQuery({
		queryKey: ["locations"],
		queryFn: () => request<LocationRead[]>("GET", "/api/v1/locations"),
	});

	if (entriesQuery.isPending || locationsQuery.isPending) {
		return <p>Loading history…</p>;
	}
	if (entriesQuery.isError) {
		return <p role="alert">{problemMessage(entriesQuery.error)}</p>;
	}
	if (locationsQuery.isError) {
		return <p role="alert">{problemMessage(locationsQuery.error)}</p>;
	}

	const locationNames = new Map(
		locationsQuery.data.map((location) => [location.id, location.name]),
	);

	return (
		<section className="flex flex-col gap-3">
			<h2 className="text-lg font-semibold">History</h2>
			{entriesQuery.data.length === 0 ? (
				<p className="text-sm text-muted-foreground">No entries yet.</p>
			) : (
				entriesQuery.data.map((entry) => (
					<EntryCard
						key={entry.entry_id}
						entry={entry}
						locationName={
							entry.location_id !== null
								? locationNames.get(entry.location_id)
								: undefined
						}
					/>
				))
			)}
		</section>
	);
}

function EntryCard({
	entry,
	locationName,
}: {
	entry: EntryRead;
	locationName: string | undefined;
}) {
	const queryClient = useQueryClient();
	// The POST already committed the reversal, so hide Undo as soon as it
	// succeeds rather than waiting on a refetch — a reversal is rejected
	// server-side as already voided, but a stale card that still shows an
	// enabled Undo invites a confusing second click. Invalidations are fired
	// without `throwOnError`: a refetch failure surfaces as this section's
	// own query error state, not as a reason to leave Undo retryable.
	const [locallyVoided, setLocallyVoided] = useState(false);
	const undo = useMutation({
		mutationFn: () => {
			const body: ReversalCreate = { entry_id: entry.entry_id };
			return request<ReversalRead>("POST", "/api/v1/reversals", body);
		},
		onSuccess: () => {
			setLocallyVoided(true);
			void queryClient.invalidateQueries({ queryKey: ["stock"] });
			void queryClient.invalidateQueries({ queryKey: ["entries"] });
		},
	});

	const handleUndo = () => {
		if (window.confirm("Undo this entry?")) {
			undo.mutate();
		}
	};

	return (
		<Card>
			<CardHeader>
				<CardTitle className="flex items-center justify-between gap-2">
					<span className="capitalize">{entry.kind}</span>
					{entry.voided ? <Badge variant="secondary">Voided</Badge> : null}
				</CardTitle>
			</CardHeader>
			<CardContent className="flex flex-col gap-1">
				<p className="min-w-0 break-words text-sm text-muted-foreground">
					{localDate(entry.created_at)}
					{locationName ? ` · ${locationName}` : ""}
				</p>
				{entry.revenue_cents !== null ? (
					<p className="text-sm">Revenue {formatCents(entry.revenue_cents)}</p>
				) : null}
				{entry.profit_cents !== null ? (
					<p className="text-sm">Profit {formatCents(entry.profit_cents)}</p>
				) : null}
				{canUndo(entry) && !locallyVoided ? (
					<Button
						type="button"
						size="sm"
						variant="outline"
						className="mt-1 self-start"
						aria-label={`Undo ${entry.kind} ${entry.entry_id}`}
						onClick={handleUndo}
						disabled={undo.isPending}
					>
						{undo.isPending ? "Undoing…" : "Undo"}
					</Button>
				) : null}
				{undo.isError ? (
					<p role="alert" className="text-sm text-destructive">
						{problemMessage(undo.error)}
					</p>
				) : null}
			</CardContent>
		</Card>
	);
}

/** Undo targets a bake, visit, or manual entry; a reversal is never undone (docs/data-model.md). */
function canUndo(entry: EntryRead): boolean {
	return !entry.voided && entry.kind !== "reversal";
}

/** `created_at` is an ISO instant; render it as the viewer's local calendar date. */
function localDate(createdAt: string): string {
	return new Date(createdAt).toLocaleDateString();
}
