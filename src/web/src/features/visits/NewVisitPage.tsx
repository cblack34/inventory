import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { request } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/button";
import { problemMessage } from "@/lib/problemMessage";
import { MarketVisitForm } from "./MarketVisitForm";
import { StandVisitForm } from "./StandVisitForm";

type LocationRead = components["schemas"]["LocationRead"];

/**
 * `/visits/new`: pick an active stand or market, then render that
 * location's form. Kind is not a separate choice — a location's own `kind`
 * says whether the rest of this screen is a stand or market visit — so
 * picking a location is the entire first step.
 */
export function NewVisitPage() {
	const locationsQuery = useQuery({
		queryKey: ["locations"],
		queryFn: () => request<LocationRead[]>("GET", "/api/v1/locations"),
	});
	const [locationId, setLocationId] = useState<number | undefined>();

	if (locationsQuery.isPending) {
		return <p>Loading locations…</p>;
	}
	if (locationsQuery.isError && locationsQuery.data === undefined) {
		return <p role="alert">{problemMessage(locationsQuery.error)}</p>;
	}

	const options = (locationsQuery.data ?? []).filter(
		(location) =>
			location.active &&
			(location.kind === "stand" || location.kind === "market"),
	);
	const selected = options.find((location) => location.id === locationId);

	if (!selected) {
		return (
			<div className="flex flex-col gap-4">
				<h1 className="text-xl font-semibold">New visit</h1>
				{options.length === 0 ? (
					<p className="text-sm text-muted-foreground">
						No active stands or markets yet.
					</p>
				) : (
					<div className="flex flex-col gap-2">
						{options.map((location) => (
							<Button
								key={location.id}
								type="button"
								variant="outline"
								className="justify-between"
								onClick={() => setLocationId(location.id)}
							>
								{location.name}
								<span className="text-muted-foreground capitalize">
									{location.kind}
								</span>
							</Button>
						))}
					</div>
				)}
			</div>
		);
	}

	const onBack = () => setLocationId(undefined);

	return selected.kind === "stand" ? (
		<StandVisitForm
			locationId={selected.id}
			locationName={selected.name}
			onBack={onBack}
		/>
	) : (
		<MarketVisitForm
			locationId={selected.id}
			locationName={selected.name}
			onBack={onBack}
		/>
	);
}
