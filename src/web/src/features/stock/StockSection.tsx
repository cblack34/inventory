import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { request } from "@/api/client";
import type { components } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { problemMessage } from "@/lib/problemMessage";
import { summarizeBatchStates } from "./batchStateCounts";
import { TossForm } from "./TossForm";

type StockRead = components["schemas"]["StockRead"];
type SizeStockRead = components["schemas"]["SizeStockRead"];
type LocationRead = components["schemas"]["LocationRead"];

/** Stock grouped by location, in the API's own order; nothing here is derived. */
export function StockSection() {
	const stockQuery = useQuery({
		queryKey: ["stock"],
		queryFn: () => request<StockRead[]>("GET", "/api/v1/stock"),
	});
	const locationsQuery = useQuery({
		queryKey: ["locations"],
		queryFn: () => request<LocationRead[]>("GET", "/api/v1/locations"),
	});

	if (stockQuery.isPending || locationsQuery.isPending) {
		return <p>Loading stock…</p>;
	}
	if (stockQuery.isError) {
		return <p role="alert">{problemMessage(stockQuery.error)}</p>;
	}
	if (locationsQuery.isError) {
		return <p role="alert">{problemMessage(locationsQuery.error)}</p>;
	}

	const wasteLocationId = locationsQuery.data.find(
		(location) => location.kind === "waste",
	)?.id;

	return (
		<section className="flex flex-col gap-3">
			<h2 className="text-lg font-semibold">Stock</h2>
			{stockQuery.data.map((location) => (
				<LocationCard
					key={location.location_id}
					location={location}
					wasteLocationId={wasteLocationId}
				/>
			))}
		</section>
	);
}

function LocationCard({
	location,
	wasteLocationId,
}: {
	location: StockRead;
	wasteLocationId: number | undefined;
}) {
	const canToss = location.kind === "kitchen";

	return (
		<Card>
			<CardHeader>
				<CardTitle>{location.name}</CardTitle>
			</CardHeader>
			<CardContent className="flex flex-col gap-3">
				{location.sizes.length === 0 ? (
					<p className="text-sm text-muted-foreground">No stock.</p>
				) : (
					location.sizes.map((size) => (
						<SizeRow
							key={size.size_id}
							size={size}
							canToss={canToss}
							kitchenLocationId={location.location_id}
							wasteLocationId={wasteLocationId}
						/>
					))
				)}
			</CardContent>
		</Card>
	);
}

function SizeRow({
	size,
	canToss,
	kitchenLocationId,
	wasteLocationId,
}: {
	size: SizeStockRead;
	canToss: boolean;
	kitchenLocationId: number;
	wasteLocationId: number | undefined;
}) {
	const [tossing, setTossing] = useState(false);
	const { expiringSoon, expired } = summarizeBatchStates(size.batches);

	return (
		<div className="flex flex-col gap-1 border-b pb-3 last:border-b-0 last:pb-0">
			<div className="flex items-center justify-between gap-2">
				<div>
					<p className="font-medium">{size.recipe_name}</p>
					<p className="text-sm text-muted-foreground">{size.size_name}</p>
				</div>
				<div className="flex flex-wrap items-center justify-end gap-1.5">
					<span className="text-sm font-medium">{size.quantity}</span>
					{expiringSoon > 0 ? (
						<Badge variant="secondary">Expiring soon ×{expiringSoon}</Badge>
					) : null}
					{expired > 0 ? (
						<Badge variant="destructive">Expired ×{expired}</Badge>
					) : null}
				</div>
			</div>
			{canToss && wasteLocationId !== undefined ? (
				tossing ? (
					<TossForm
						sizeId={size.size_id}
						label={`${size.recipe_name} ${size.size_name}`}
						onHand={size.quantity}
						kitchenLocationId={kitchenLocationId}
						wasteLocationId={wasteLocationId}
						onCancel={() => setTossing(false)}
					/>
				) : (
					<Button
						type="button"
						size="sm"
						variant="outline"
						className="mt-1 self-start"
						aria-label={`Toss ${size.recipe_name} ${size.size_name}`}
						onClick={() => setTossing(true)}
					>
						Toss
					</Button>
				)
			) : null}
		</div>
	);
}
