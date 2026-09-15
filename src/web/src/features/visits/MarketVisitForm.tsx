import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { useNavigate } from "react-router";
import { z } from "zod";
import { request } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { problemMessage } from "@/lib/problemMessage";
import { CountField } from "./CountField";
import { parseDollarsToCents } from "./dollars";
import { buildMarketRows, countSetValueAs, normalizeCount } from "./rows";

type StockRead = components["schemas"]["StockRead"];
type RecipeRead = components["schemas"]["RecipeRead"];
type MarketVisitCreate = components["schemas"]["MarketVisitCreate"];
type VisitRead = components["schemas"]["VisitRead"];

type MarketRowMeta = {
	sizeId: number;
	label: string;
	onHand: number;
	priceCents: number;
};

type MarketVisitFormProps = {
	locationId: number;
	locationName: string;
	onBack: () => void;
};

/**
 * Loads Kitchen stock (the only source a market visit's `taken` draws from)
 * and every recipe's sizes (to know which sizes are zero-price, the only
 * signal that decides `returned`'s prefill — no `is_sample` flag anywhere).
 */
export function MarketVisitForm({
	locationId,
	locationName,
	onBack,
}: MarketVisitFormProps) {
	const stockQuery = useQuery({
		queryKey: ["stock"],
		queryFn: () => request<StockRead[]>("GET", "/api/v1/stock"),
	});
	const recipesQuery = useQuery({
		queryKey: ["recipes"],
		queryFn: () => request<RecipeRead[]>("GET", "/api/v1/recipes"),
	});

	if (stockQuery.isPending || recipesQuery.isPending) {
		return <p>Loading…</p>;
	}
	if (stockQuery.isError) {
		return <p role="alert">{problemMessage(stockQuery.error)}</p>;
	}
	if (recipesQuery.isError) {
		return <p role="alert">{problemMessage(recipesQuery.error)}</p>;
	}

	const kitchenStock = stockQuery.data.find(
		(location) => location.kind === "kitchen",
	);
	const priceBySize = new Map<number, number>();
	for (const recipe of recipesQuery.data) {
		for (const size of recipe.sizes) {
			priceBySize.set(size.id, size.price_cents);
		}
	}

	const rowsMeta: MarketRowMeta[] = (kitchenStock?.sizes ?? [])
		.filter((size) => size.quantity > 0)
		.map((size) => ({
			sizeId: size.size_id,
			label: `${size.recipe_name} — ${size.size_name}`,
			onHand: size.quantity,
			priceCents: priceBySize.get(size.size_id) ?? 0,
		}));

	return (
		<MarketVisitFormInner
			locationId={locationId}
			locationName={locationName}
			rowsMeta={rowsMeta}
			onBack={onBack}
		/>
	);
}

const countInputSchema = z.union([z.literal(""), z.number()]);

function marketVisitSchema(rowsMeta: MarketRowMeta[]) {
	return z.object({
		revenue: z
			.string()
			.min(1, "Revenue is required")
			.refine((value) => parseDollarsToCents(value) !== null, {
				message: "Enter a dollar amount like 12.34",
			}),
		fee: z
			.string()
			.min(1, "Fee is required")
			.refine((value) => parseDollarsToCents(value) !== null, {
				message: "Enter a dollar amount like 12.34",
			}),
		rows: z
			.array(
				z.object({
					sizeId: z.number(),
					taken: countInputSchema,
					returned: countInputSchema,
					tossed: countInputSchema,
				}),
			)
			.superRefine((rows, ctx) => {
				rows.forEach((row, index) => {
					const meta = rowsMeta[index];
					if (!meta) {
						return;
					}

					const taken = normalizeCount(row.taken);
					if (taken === undefined) {
						ctx.addIssue({
							code: "custom",
							message: "Enter a whole number ≥ 0",
							path: [index, "taken"],
						});
						return;
					}
					if (taken > meta.onHand) {
						ctx.addIssue({
							code: "custom",
							message: `Only ${meta.onHand} on hand in kitchen`,
							path: [index, "taken"],
						});
					}
					if (taken === 0) {
						// returned/tossed are hidden for this row and not sent.
						return;
					}

					const returned = normalizeCount(row.returned);
					if (returned === undefined) {
						ctx.addIssue({
							code: "custom",
							message:
								meta.priceCents === 0
									? "Enter a whole number ≥ 0"
									: "Returned is required",
							path: [index, "returned"],
						});
					}
					const tossed = normalizeCount(row.tossed);
					if (tossed === undefined) {
						ctx.addIssue({
							code: "custom",
							message: "Enter a whole number ≥ 0",
							path: [index, "tossed"],
						});
					}
					if (
						returned !== undefined &&
						tossed !== undefined &&
						returned + tossed > taken
					) {
						ctx.addIssue({
							code: "custom",
							message: "Returned plus tossed cannot exceed taken",
							path: [index, "returned"],
						});
					}
				});
			}),
	});
}

type MarketFormValues = z.infer<ReturnType<typeof marketVisitSchema>>;

function MarketVisitFormInner({
	locationId,
	locationName,
	rowsMeta: rowsMetaProp,
	onBack,
}: {
	locationId: number;
	locationName: string;
	rowsMeta: MarketRowMeta[];
	onBack: () => void;
}) {
	// Captured once at mount: a background `["stock"]` refetch (window focus,
	// another tab's mutation) must never reshuffle which row index a form
	// value or a validation limit belongs to. See `StandVisitForm`'s loader
	// comment for the same reasoning.
	const [rowsMeta] = useState(() => rowsMetaProp);
	const queryClient = useQueryClient();
	const navigate = useNavigate();
	const {
		register,
		handleSubmit,
		control,
		formState: { errors },
	} = useForm<MarketFormValues>({
		resolver: zodResolver(marketVisitSchema(rowsMeta)),
		defaultValues: {
			revenue: "",
			fee: "",
			rows: rowsMeta.map((meta) => ({
				sizeId: meta.sizeId,
				taken: 0,
				returned: meta.priceCents === 0 ? 0 : "",
				tossed: 0,
			})),
		},
	});
	const watchedRows = useWatch({ control, name: "rows" }) ?? [];

	const mutation = useMutation({
		mutationFn: (body: MarketVisitCreate) =>
			request<VisitRead>("POST", "/api/v1/visits", body),
		onSuccess: (visit) => {
			void queryClient.invalidateQueries({ queryKey: ["stock"] });
			void queryClient.invalidateQueries({ queryKey: ["entries"] });
			navigate(`/visits/${visit.entry_id}`);
		},
	});

	const onSubmit = handleSubmit((values) => {
		const revenueCents = parseDollarsToCents(values.revenue);
		const feeCents = parseDollarsToCents(values.fee);
		if (revenueCents === null || feeCents === null) {
			// Unreachable once zod has validated `revenue`/`fee`; guards the type.
			return;
		}
		mutation.mutate({
			kind: "market",
			location_id: locationId,
			rows: buildMarketRows(values.rows),
			revenue_cents: revenueCents,
			fee_cents: feeCents,
		});
	});

	return (
		<div className="flex flex-col gap-4">
			<div className="flex items-center justify-between gap-2">
				<h1 className="text-xl font-semibold">Market visit — {locationName}</h1>
				<Button type="button" variant="ghost" size="sm" onClick={onBack}>
					Change location
				</Button>
			</div>
			<form onSubmit={onSubmit} className="flex flex-col gap-4">
				<Card>
					<CardHeader>
						<CardTitle>Taken from kitchen</CardTitle>
					</CardHeader>
					<CardContent className="flex flex-col gap-4">
						{rowsMeta.length === 0 ? (
							<p className="text-sm text-muted-foreground">
								Nothing on hand in the kitchen.
							</p>
						) : (
							rowsMeta.map((meta, index) => {
								const currentRow = watchedRows[index];
								const taken = normalizeCount(currentRow?.taken ?? 0) ?? 0;
								return (
									<div
										key={meta.sizeId}
										className="flex flex-col gap-2 border-b pb-3 last:border-b-0 last:pb-0"
									>
										<p className="font-medium">
											{meta.label} · kitchen on hand {meta.onHand}
										</p>
										<CountField
											id={`taken-${meta.sizeId}`}
											label="Taken"
											error={errors.rows?.[index]?.taken?.message}
											inputProps={register(`rows.${index}.taken`, {
												setValueAs: countSetValueAs,
											})}
										/>
										{taken > 0 ? (
											<>
												<CountField
													id={`returned-${meta.sizeId}`}
													label={
														meta.priceCents === 0
															? "Returned"
															: "Returned (required)"
													}
													error={errors.rows?.[index]?.returned?.message}
													inputProps={register(`rows.${index}.returned`, {
														setValueAs: countSetValueAs,
													})}
												/>
												<CountField
													id={`tossed-${meta.sizeId}`}
													label="Tossed"
													error={errors.rows?.[index]?.tossed?.message}
													inputProps={register(`rows.${index}.tossed`, {
														setValueAs: countSetValueAs,
													})}
												/>
											</>
										) : null}
									</div>
								);
							})
						)}
					</CardContent>
				</Card>
				<div className="flex flex-col gap-1">
					<Label htmlFor="revenue">Revenue</Label>
					<Input
						id="revenue"
						inputMode="decimal"
						placeholder="0.00"
						aria-invalid={errors.revenue ? true : undefined}
						aria-describedby={errors.revenue ? "revenue-error" : undefined}
						{...register("revenue")}
					/>
					{errors.revenue ? (
						<p
							id="revenue-error"
							role="alert"
							className="text-sm text-destructive"
						>
							{errors.revenue.message}
						</p>
					) : null}
				</div>
				<div className="flex flex-col gap-1">
					<Label htmlFor="fee">Booth fee</Label>
					<Input
						id="fee"
						inputMode="decimal"
						placeholder="0.00"
						aria-invalid={errors.fee ? true : undefined}
						aria-describedby={errors.fee ? "fee-error" : undefined}
						{...register("fee")}
					/>
					{errors.fee ? (
						<p id="fee-error" role="alert" className="text-sm text-destructive">
							{errors.fee.message}
						</p>
					) : null}
				</div>
				{mutation.isError ? (
					<p role="alert" className="text-sm text-destructive">
						{problemMessage(mutation.error)}
					</p>
				) : null}
				<Button type="submit" disabled={mutation.isPending}>
					{mutation.isPending ? "Saving…" : "Save visit"}
				</Button>
			</form>
		</div>
	);
}
