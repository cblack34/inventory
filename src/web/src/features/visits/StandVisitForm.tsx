import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router";
import { z } from "zod";
import { request } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { parseDollarsToCents } from "@/lib/dollars";
import { problemMessage } from "@/lib/problemMessage";
import { CountField } from "./CountField";
import { buildStandRows } from "./rows";

type StockRead = components["schemas"]["StockRead"];
type StandVisitCreate = components["schemas"]["StandVisitCreate"];
type VisitRead = components["schemas"]["VisitRead"];

type RowMeta = { sizeId: number; label: string; onHand: number };

type StandVisitFormProps = {
	locationId: number;
	locationName: string;
	onBack: () => void;
};

/**
 * Loads the stock this form needs — the stand's own on-hand (section A) and
 * Kitchen's on-hand (section B) — then hands fixed row lists to the actual
 * form. Splitting the query from the form means a background stock refetch
 * never clobbers what the user has already typed.
 */
export function StandVisitForm({
	locationId,
	locationName,
	onBack,
}: StandVisitFormProps) {
	const stockQuery = useQuery({
		queryKey: ["stock"],
		queryFn: () => request<StockRead[]>("GET", "/api/v1/stock"),
	});

	// ponytail: `["stock"]` is often already cached by Home, so `isPending`
	// goes false immediately while this screen's own mount-time refetch is
	// still in flight. Wait for that refetch to settle once before mounting
	// the inner form below, so the on-hand snapshot it freezes on mount
	// reflects this page's own fetch rather than a stale cache from another
	// screen. Once settled, a later background refetch never unsettles this —
	// the inner form stays mounted and keeps its already-frozen snapshot.
	const [hasSettled, setHasSettled] = useState(false);
	useEffect(() => {
		if (!stockQuery.isFetching) {
			setHasSettled(true);
		}
	}, [stockQuery.isFetching]);

	if (stockQuery.isPending || !hasSettled) {
		return <p>Loading stock…</p>;
	}
	if (stockQuery.isError && stockQuery.data === undefined) {
		return <p role="alert">{problemMessage(stockQuery.error)}</p>;
	}

	const standStock = stockQuery.data.find(
		(location) => location.location_id === locationId,
	);
	const kitchenStock = stockQuery.data.find(
		(location) => location.kind === "kitchen",
	);

	const sectionA: RowMeta[] = (standStock?.sizes ?? [])
		.filter((size) => size.quantity > 0)
		.map((size) => ({
			sizeId: size.size_id,
			label: `${size.recipe_name} — ${size.size_name}`,
			onHand: size.quantity,
		}));
	const sectionB: RowMeta[] = (kitchenStock?.sizes ?? [])
		.filter((size) => size.quantity > 0)
		.map((size) => ({
			sizeId: size.size_id,
			label: `${size.recipe_name} — ${size.size_name}`,
			onHand: size.quantity,
		}));

	return (
		<StandVisitFormInner
			locationId={locationId}
			locationName={locationName}
			sectionA={sectionA}
			sectionB={sectionB}
			onBack={onBack}
		/>
	);
}

function standVisitSchema(sectionA: RowMeta[], sectionB: RowMeta[]) {
	return z.object({
		revenue: z
			.string()
			.min(1, "Cash collected is required")
			.refine((value) => parseDollarsToCents(value) !== null, {
				message: "Enter a dollar amount like 12.34",
			})
			.refine((value) => (parseDollarsToCents(value) ?? -1) >= 0, {
				message: "Must be zero or more",
			}),
		rows: z
			.array(
				z.object({
					sizeId: z.number(),
					counted: z.number(),
					tossed: z.number(),
					pulled: z.number(),
				}),
			)
			.superRefine((rows, ctx) => {
				rows.forEach((row, index) => {
					const meta = sectionA[index];
					if (!meta) {
						return;
					}
					if (!Number.isInteger(row.counted) || row.counted < 0) {
						ctx.addIssue({
							code: "custom",
							message: "Enter a whole number ≥ 0",
							path: [index, "counted"],
						});
						return;
					}
					if (row.counted > meta.onHand) {
						ctx.addIssue({
							code: "custom",
							message: `Only ${meta.onHand} on hand`,
							path: [index, "counted"],
						});
					}
					if (!Number.isInteger(row.tossed) || row.tossed < 0) {
						ctx.addIssue({
							code: "custom",
							message: "Enter a whole number ≥ 0",
							path: [index, "tossed"],
						});
					}
					if (!Number.isInteger(row.pulled) || row.pulled < 0) {
						ctx.addIssue({
							code: "custom",
							message: "Enter a whole number ≥ 0",
							path: [index, "pulled"],
						});
					}
					if (row.tossed + row.pulled > row.counted) {
						ctx.addIssue({
							code: "custom",
							message: "Tossed plus pulled cannot exceed counted",
							path: [index, "tossed"],
						});
					}
				});
			}),
		addedRows: z
			.array(
				z.object({
					sizeId: z.number(),
					added: z.number(),
				}),
			)
			.superRefine((rows, ctx) => {
				rows.forEach((row, index) => {
					const meta = sectionB[index];
					if (!meta) {
						return;
					}
					if (!Number.isInteger(row.added) || row.added < 0) {
						ctx.addIssue({
							code: "custom",
							message: "Enter a whole number ≥ 0",
							path: [index, "added"],
						});
						return;
					}
					if (row.added > meta.onHand) {
						ctx.addIssue({
							code: "custom",
							message: `Only ${meta.onHand} on hand in kitchen`,
							path: [index, "added"],
						});
					}
				});
			}),
	});
}

type StandFormValues = z.infer<ReturnType<typeof standVisitSchema>>;

function StandVisitFormInner({
	locationId,
	locationName,
	sectionA: sectionAProp,
	sectionB: sectionBProp,
	onBack,
}: {
	locationId: number;
	locationName: string;
	sectionA: RowMeta[];
	sectionB: RowMeta[];
	onBack: () => void;
}) {
	// Captured once at mount: a background `["stock"]` refetch (window focus,
	// another tab's mutation) that inserts or removes a size must never
	// reshuffle which row index a form value or a validation limit belongs
	// to. See the loader comment above for why the query is split from this
	// component in the first place.
	const [sectionA] = useState(() => sectionAProp);
	const [sectionB] = useState(() => sectionBProp);
	const queryClient = useQueryClient();
	const navigate = useNavigate();
	const {
		register,
		handleSubmit,
		formState: { errors },
	} = useForm<StandFormValues>({
		resolver: zodResolver(standVisitSchema(sectionA, sectionB)),
		defaultValues: {
			revenue: "",
			rows: sectionA.map((row) => ({
				sizeId: row.sizeId,
				counted: row.onHand,
				tossed: 0,
				pulled: 0,
			})),
			addedRows: sectionB.map((row) => ({ sizeId: row.sizeId, added: 0 })),
		},
	});

	const mutation = useMutation({
		mutationFn: (body: StandVisitCreate) =>
			request<VisitRead>("POST", "/api/v1/visits", body),
		onSuccess: (visit) => {
			void queryClient.invalidateQueries({ queryKey: ["stock"] });
			void queryClient.invalidateQueries({ queryKey: ["entries"] });
			navigate(`/visits/${visit.entry_id}`);
		},
	});

	const onSubmit = handleSubmit((values) => {
		const revenueCents = parseDollarsToCents(values.revenue);
		if (revenueCents === null) {
			// Unreachable once zod has validated `revenue`; guards the type.
			return;
		}
		mutation.mutate({
			kind: "stand",
			location_id: locationId,
			rows: buildStandRows(values.rows, values.addedRows),
			revenue_cents: revenueCents,
		});
	});

	return (
		<div className="flex flex-col gap-4">
			<div className="flex items-center justify-between gap-2">
				<h1 className="text-xl font-semibold">Stand visit — {locationName}</h1>
				<Button type="button" variant="ghost" size="sm" onClick={onBack}>
					Change location
				</Button>
			</div>
			<form onSubmit={onSubmit} className="flex flex-col gap-4">
				<Card>
					<CardHeader>
						<CardTitle>On hand at {locationName}</CardTitle>
					</CardHeader>
					<CardContent className="flex flex-col gap-4">
						{sectionA.length === 0 ? (
							<p className="text-sm text-muted-foreground">
								Nothing on hand here yet.
							</p>
						) : (
							sectionA.map((row, index) => (
								<div
									key={row.sizeId}
									className="flex flex-col gap-2 border-b pb-3 last:border-b-0 last:pb-0"
								>
									<p className="font-medium">
										{row.label} · on hand {row.onHand}
									</p>
									<CountField
										id={`counted-${row.sizeId}`}
										label="Counted"
										error={errors.rows?.[index]?.counted?.message}
										inputProps={register(`rows.${index}.counted`, {
											valueAsNumber: true,
										})}
									/>
									<CountField
										id={`tossed-${row.sizeId}`}
										label="Tossed"
										error={errors.rows?.[index]?.tossed?.message}
										inputProps={register(`rows.${index}.tossed`, {
											valueAsNumber: true,
										})}
									/>
									<CountField
										id={`pulled-${row.sizeId}`}
										label="Pulled to kitchen"
										error={errors.rows?.[index]?.pulled?.message}
										inputProps={register(`rows.${index}.pulled`, {
											valueAsNumber: true,
										})}
									/>
								</div>
							))
						)}
					</CardContent>
				</Card>
				<Card>
					<CardHeader>
						<CardTitle>Add from kitchen</CardTitle>
					</CardHeader>
					<CardContent className="flex flex-col gap-4">
						{sectionB.length === 0 ? (
							<p className="text-sm text-muted-foreground">
								Nothing on hand in the kitchen.
							</p>
						) : (
							sectionB.map((row, index) => (
								<div
									key={row.sizeId}
									className="flex flex-col gap-2 border-b pb-3 last:border-b-0 last:pb-0"
								>
									<p className="font-medium">
										{row.label} · kitchen on hand {row.onHand}
									</p>
									<CountField
										id={`added-${row.sizeId}`}
										label="Added to stand"
										error={errors.addedRows?.[index]?.added?.message}
										inputProps={register(`addedRows.${index}.added`, {
											valueAsNumber: true,
										})}
									/>
								</div>
							))
						)}
					</CardContent>
				</Card>
				<div className="flex flex-col gap-1">
					<Label htmlFor="revenue">Cash collected</Label>
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
