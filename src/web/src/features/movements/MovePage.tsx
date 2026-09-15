import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { request } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { problemMessage } from "@/lib/problemMessage";

type StockRead = components["schemas"]["StockRead"];
type LocationRead = components["schemas"]["LocationRead"];
type MovementCreate = components["schemas"]["MovementCreate"];
type EntryRead = components["schemas"]["EntryRead"];

/** Kinds that are always legal manual-move destinations, regardless of `active`. */
const REMOVAL_KINDS = new Set(["waste", "sold", "sampled"]);

/**
 * A destination is an active kitchen/stand that isn't the source, or one of
 * the three removal kinds. Markets and Production never appear here: a
 * manual move never targets a market (only a market visit's `taken` step
 * does), and Production only ever receives nothing manually.
 */
function isValidDestination(
	location: LocationRead,
	sourceLocationId: number,
): boolean {
	if (location.id === sourceLocationId) {
		return false;
	}
	if (REMOVAL_KINDS.has(location.kind)) {
		return true;
	}
	return (
		(location.kind === "kitchen" || location.kind === "stand") &&
		location.active
	);
}

/** `/move`: transfer stock between inventory locations, or remove it to Waste/Sold/Sampled. */
export function MovePage() {
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

	// Only (location, size) pairs with quantity > 0 are valid move sources.
	const sources = stockQuery.data
		.map((location) => ({
			...location,
			sizes: location.sizes.filter((size) => size.quantity > 0),
		}))
		.filter((location) => location.sizes.length > 0);

	const firstSource = sources[0];
	if (firstSource === undefined) {
		return <p className="text-sm text-muted-foreground">No stock to move.</p>;
	}

	return (
		<div className="flex flex-col gap-4">
			<h1 className="text-xl font-semibold">Move</h1>
			<MoveForm
				sources={sources}
				firstSource={firstSource}
				locations={locationsQuery.data}
			/>
		</div>
	);
}

type MoveFormValues = {
	quantity: number;
};

function moveSchema(onHand: number) {
	return z.object({
		quantity: z
			.number()
			.int("Enter a whole number")
			.min(1, "Enter a number greater than zero")
			.max(onHand, `Only ${onHand} on hand`),
	});
}

/**
 * Source, size, destination, and quantity. Only recipe/size/count and a
 * quantity ever reach the API (`MovementCreate`) — FIFO batch selection is
 * entirely server-side (non-negotiable 3), so nothing here ever names a batch.
 */
function MoveForm({
	sources,
	firstSource,
	locations,
}: {
	sources: StockRead[];
	firstSource: StockRead;
	locations: LocationRead[];
}) {
	const queryClient = useQueryClient();
	const [sourceLocationId, setSourceLocationId] = useState(
		firstSource.location_id,
	);
	const source =
		sources.find((s) => s.location_id === sourceLocationId) ?? firstSource;
	const firstSize = source.sizes[0];

	const [sizeId, setSizeId] = useState(firstSize?.size_id);
	const size = source.sizes.find((s) => s.size_id === sizeId) ?? firstSize;

	const destinations = locations.filter((location) =>
		isValidDestination(location, source.location_id),
	);
	const firstDestination = destinations[0];
	const [destinationId, setDestinationId] = useState(firstDestination?.id);
	const destination =
		destinations.find((d) => d.id === destinationId) ?? firstDestination;

	const onHand = size?.quantity ?? 0;

	const {
		register,
		handleSubmit,
		reset,
		formState: { errors },
	} = useForm<MoveFormValues>({
		resolver: zodResolver(moveSchema(onHand)),
		defaultValues: { quantity: 1 },
	});

	const move = useMutation({
		mutationFn: (values: MoveFormValues) => {
			if (size === undefined || destination === undefined) {
				throw new Error("Choose a source, size, and destination first");
			}
			const body: MovementCreate = {
				from_location_id: source.location_id,
				to_location_id: destination.id,
				size_id: size.size_id,
				quantity: values.quantity,
			};
			return request<EntryRead>("POST", "/api/v1/movements", body);
		},
		onSuccess: () => {
			reset({ quantity: 1 });
			void queryClient.invalidateQueries({ queryKey: ["stock"] });
			void queryClient.invalidateQueries({ queryKey: ["entries"] });
		},
	});

	function handleSourceChange(newSourceId: number) {
		setSourceLocationId(newSourceId);
		const newSource =
			sources.find((s) => s.location_id === newSourceId) ?? firstSource;
		setSizeId(newSource.sizes[0]?.size_id);
		const newDestinations = locations.filter((location) =>
			isValidDestination(location, newSourceId),
		);
		setDestinationId(newDestinations[0]?.id);
	}

	const onSubmit = handleSubmit((values) => move.mutate(values));

	return (
		<form onSubmit={onSubmit} className="flex flex-col gap-4">
			<div className="flex flex-col gap-1.5">
				<Label htmlFor="source">From</Label>
				<NativeSelect
					id="source"
					value={source.location_id}
					onChange={(event) => handleSourceChange(Number(event.target.value))}
				>
					{sources.map((s) => (
						<option key={s.location_id} value={s.location_id}>
							{s.name}
						</option>
					))}
				</NativeSelect>
			</div>
			<div className="flex flex-col gap-1.5">
				<Label htmlFor="size">Item</Label>
				<NativeSelect
					id="size"
					value={size?.size_id}
					onChange={(event) => setSizeId(Number(event.target.value))}
				>
					{source.sizes.map((s) => (
						<option key={s.size_id} value={s.size_id}>
							{s.recipe_name} {s.size_name} ({s.quantity} on hand)
						</option>
					))}
				</NativeSelect>
			</div>
			<div className="flex flex-col gap-1.5">
				<Label htmlFor="destination">To</Label>
				<NativeSelect
					id="destination"
					value={destination?.id}
					onChange={(event) => setDestinationId(Number(event.target.value))}
				>
					{destinations.map((d) => (
						<option key={d.id} value={d.id}>
							{d.name}
						</option>
					))}
				</NativeSelect>
			</div>
			<div className="flex flex-col gap-1.5">
				<Label htmlFor="quantity">Quantity</Label>
				<Input
					id="quantity"
					type="number"
					inputMode="numeric"
					aria-invalid={errors.quantity ? true : undefined}
					aria-describedby={errors.quantity ? "quantity-error" : undefined}
					{...register("quantity", { valueAsNumber: true })}
				/>
				{errors.quantity ? (
					<p
						id="quantity-error"
						role="alert"
						className="text-sm text-destructive"
					>
						{errors.quantity.message}
					</p>
				) : null}
			</div>
			{move.isError ? (
				<p role="alert" className="text-sm text-destructive">
					{problemMessage(move.error)}
				</p>
			) : null}
			<Button
				type="submit"
				disabled={move.isPending || destination === undefined}
			>
				{move.isPending ? "Moving…" : "Move"}
			</Button>
		</form>
	);
}
