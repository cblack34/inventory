import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router";
import { request } from "@/api/client";
import type { components } from "@/api/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCents } from "@/lib/money";
import { problemMessage } from "@/lib/problemMessage";

type VisitRead = components["schemas"]["VisitRead"];
type LocationRead = components["schemas"]["LocationRead"];

/**
 * `/visits/:entryId`: renders `GET /api/v1/visits/{id}` exactly as
 * returned. No number here is recomputed client-side — expected revenue,
 * the difference, and the three profit lines are all server truth.
 */
export function VisitDetailPage() {
	const { entryId } = useParams<{ entryId: string }>();
	const visitId = Number(entryId);

	const visitQuery = useQuery({
		queryKey: ["visit", visitId],
		queryFn: () => request<VisitRead>("GET", `/api/v1/visits/${visitId}`),
		enabled: Number.isInteger(visitId),
	});
	const locationsQuery = useQuery({
		queryKey: ["locations"],
		queryFn: () => request<LocationRead[]>("GET", "/api/v1/locations"),
	});

	if (!Number.isInteger(visitId)) {
		return <p role="alert">Invalid visit id.</p>;
	}
	if (visitQuery.isPending) {
		return <p>Loading visit…</p>;
	}
	if (visitQuery.isError) {
		return <p role="alert">{problemMessage(visitQuery.error)}</p>;
	}

	// The location name is decoration; the visit renders as soon as its own
	// query succeeds, whatever the locations query is doing.
	const visit = visitQuery.data;
	const locationName = locationsQuery.data?.find(
		(location) => location.id === visit.location_id,
	)?.name;
	const differenceLabel = visit.kind === "stand" ? "Shrink" : "Difference";

	return (
		<div className="flex flex-col gap-4">
			<h1 className="text-xl font-semibold">
				{visit.kind === "stand" ? "Stand visit" : "Market visit"}
				{locationName ? ` — ${locationName}` : ""}
			</h1>
			<Card>
				<CardHeader>
					<CardTitle>Revenue</CardTitle>
				</CardHeader>
				<CardContent className="flex flex-col gap-1">
					<p>Cash collected: {formatCents(visit.revenue_cents)}</p>
					{visit.kind === "market" ? (
						<p>Fee: {formatCents(visit.fee_cents)}</p>
					) : null}
					<p>Expected revenue: {formatCents(visit.expected_revenue_cents)}</p>
					<p>
						{differenceLabel}: {formatCents(visit.difference_cents)}
					</p>
				</CardContent>
			</Card>
			<Card>
				<CardHeader>
					<CardTitle>Profit</CardTitle>
				</CardHeader>
				<CardContent className="flex flex-col gap-1">
					{visit.profit ? (
						<>
							<p>Sold cost: {formatCents(visit.profit.sold_cost_cents)}</p>
							<p>Waste cost: {formatCents(visit.profit.waste_cost_cents)}</p>
							<p>
								Sampled cost: {formatCents(visit.profit.sampled_cost_cents)}
							</p>
							<p className="font-medium">
								Profit: {formatCents(visit.profit.profit_cents)}
							</p>
						</>
					) : (
						<p className="text-sm text-muted-foreground">
							Voided — no profit shown.
						</p>
					)}
				</CardContent>
			</Card>
		</div>
	);
}
