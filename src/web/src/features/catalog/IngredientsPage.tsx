import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { request } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { centsToDollarsInput, parseDollarsToCents } from "@/lib/dollars";
import { formatCents } from "@/lib/money";
import { problemMessage } from "@/lib/problemMessage";

type IngredientRead = components["schemas"]["IngredientRead"];
type IngredientCreate = components["schemas"]["IngredientCreate"];
type IngredientUpdate = components["schemas"]["IngredientUpdate"];

const dollarsSchema = z
	.string()
	.min(1, "Required")
	.refine((value) => parseDollarsToCents(value) !== null, {
		message: "Enter a dollar amount like 1.23",
	})
	.refine((value) => (parseDollarsToCents(value) ?? -1) >= 0, {
		message: "Must be zero or more",
	});

/** Parses a dollars string already validated by `dollarsSchema`, never `null` in practice. */
function centsOrThrow(dollars: string): number {
	const cents = parseDollarsToCents(dollars);
	if (cents === null) {
		throw new Error(`Invalid dollars value after validation: ${dollars}`);
	}
	return cents;
}

const ingredientSchema = z.object({
	name: z.string().min(1, "Required"),
	unitLabel: z.string().min(1, "Required"),
	priceDollars: dollarsSchema,
});

type IngredientFormValues = z.infer<typeof ingredientSchema>;

/** Ingredients: list, create, and edit (name, unit label, price, active flag). */
export function IngredientsPage() {
	const ingredientsQuery = useQuery({
		queryKey: ["ingredients"],
		queryFn: () => request<IngredientRead[]>("GET", "/api/v1/ingredients"),
	});

	return (
		<div className="flex flex-col gap-6">
			<h1 className="text-xl font-semibold">Ingredients</h1>
			<CreateIngredientForm />
			{ingredientsQuery.isPending ? <p>Loading ingredients…</p> : null}
			{ingredientsQuery.isError ? (
				<p role="alert">{problemMessage(ingredientsQuery.error)}</p>
			) : null}
			{ingredientsQuery.data ? (
				<section className="flex flex-col gap-3">
					{ingredientsQuery.data.length === 0 ? (
						<p className="text-sm text-muted-foreground">No ingredients yet.</p>
					) : (
						ingredientsQuery.data.map((ingredient) => (
							<IngredientRow key={ingredient.id} ingredient={ingredient} />
						))
					)}
				</section>
			) : null}
		</div>
	);
}

function CreateIngredientForm() {
	const queryClient = useQueryClient();
	const {
		register,
		handleSubmit,
		reset,
		formState: { errors },
	} = useForm<IngredientFormValues>({
		resolver: zodResolver(ingredientSchema),
		defaultValues: { name: "", unitLabel: "", priceDollars: "0" },
	});

	const create = useMutation({
		mutationFn: (values: IngredientFormValues) => {
			const body: IngredientCreate = {
				name: values.name,
				unit_label: values.unitLabel,
				current_price_cents: centsOrThrow(values.priceDollars),
			};
			return request<IngredientRead>("POST", "/api/v1/ingredients", body);
		},
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: ["ingredients"] });
			reset({ name: "", unitLabel: "", priceDollars: "0" });
		},
	});

	const onSubmit = handleSubmit((values) => create.mutate(values));

	return (
		<Card>
			<CardHeader>
				<CardTitle asChild>
					<h2>Add ingredient</h2>
				</CardTitle>
			</CardHeader>
			<CardContent>
				<form onSubmit={onSubmit} className="flex flex-col gap-3">
					<div className="flex flex-col gap-1.5">
						<Label htmlFor="new-ingredient-name">Name</Label>
						<Input
							id="new-ingredient-name"
							aria-invalid={errors.name ? true : undefined}
							{...register("name")}
						/>
						{errors.name ? (
							<p role="alert" className="text-sm text-destructive">
								{errors.name.message}
							</p>
						) : null}
					</div>
					<div className="flex flex-col gap-1.5">
						<Label htmlFor="new-ingredient-unit">Unit label</Label>
						<Input
							id="new-ingredient-unit"
							placeholder="gram, teaspoon, …"
							aria-invalid={errors.unitLabel ? true : undefined}
							{...register("unitLabel")}
						/>
						{errors.unitLabel ? (
							<p role="alert" className="text-sm text-destructive">
								{errors.unitLabel.message}
							</p>
						) : null}
					</div>
					<div className="flex flex-col gap-1.5">
						<Label htmlFor="new-ingredient-price">Price per unit ($)</Label>
						<Input
							id="new-ingredient-price"
							type="text"
							inputMode="decimal"
							aria-invalid={errors.priceDollars ? true : undefined}
							{...register("priceDollars")}
						/>
						{errors.priceDollars ? (
							<p role="alert" className="text-sm text-destructive">
								{errors.priceDollars.message}
							</p>
						) : null}
					</div>
					{create.isError ? (
						<p role="alert" className="text-sm text-destructive">
							{problemMessage(create.error)}
						</p>
					) : null}
					<Button
						type="submit"
						disabled={create.isPending}
						className="self-start"
					>
						{create.isPending ? "Adding…" : "Add ingredient"}
					</Button>
				</form>
			</CardContent>
		</Card>
	);
}

function IngredientRow({ ingredient }: { ingredient: IngredientRead }) {
	const [editing, setEditing] = useState(false);

	if (editing) {
		return (
			<EditIngredientForm
				ingredient={ingredient}
				onDone={() => setEditing(false)}
			/>
		);
	}

	return (
		<Card>
			<CardHeader>
				<CardTitle className="flex items-center justify-between gap-2">
					<span className="min-w-0 break-words">{ingredient.name}</span>
					{!ingredient.active ? (
						<span className="text-xs text-muted-foreground">Inactive</span>
					) : null}
				</CardTitle>
			</CardHeader>
			<CardContent className="flex flex-col gap-2">
				<p className="text-sm text-muted-foreground">
					{formatCents(ingredient.current_price_cents)} /{" "}
					{ingredient.unit_label}
				</p>
				<Button
					type="button"
					size="sm"
					variant="outline"
					className="self-start"
					aria-label={`Edit ${ingredient.name}`}
					onClick={() => setEditing(true)}
				>
					Edit
				</Button>
			</CardContent>
		</Card>
	);
}

function EditIngredientForm({
	ingredient,
	onDone,
}: {
	ingredient: IngredientRead;
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const {
		register,
		handleSubmit,
		control,
		formState: { errors },
	} = useForm<IngredientFormValues & { active: boolean }>({
		resolver: zodResolver(ingredientSchema.extend({ active: z.boolean() })),
		defaultValues: {
			name: ingredient.name,
			unitLabel: ingredient.unit_label,
			priceDollars: centsToDollarsInput(ingredient.current_price_cents),
			active: ingredient.active,
		},
	});

	const update = useMutation({
		mutationFn: (values: IngredientFormValues & { active: boolean }) => {
			const body: IngredientUpdate = {
				name: values.name,
				unit_label: values.unitLabel,
				current_price_cents: centsOrThrow(values.priceDollars),
				active: values.active,
			};
			return request<IngredientRead>(
				"PATCH",
				`/api/v1/ingredients/${ingredient.id}`,
				body,
			);
		},
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: ["ingredients"] });
			onDone();
		},
	});

	const onSubmit = handleSubmit((values) => update.mutate(values));

	return (
		<Card>
			<CardHeader>
				<CardTitle asChild>
					<h2 className="min-w-0 break-words">Edit {ingredient.name}</h2>
				</CardTitle>
			</CardHeader>
			<CardContent>
				<form onSubmit={onSubmit} className="flex flex-col gap-3">
					<div className="flex flex-col gap-1.5">
						<Label htmlFor={`edit-ingredient-name-${ingredient.id}`}>
							Name
						</Label>
						<Input
							id={`edit-ingredient-name-${ingredient.id}`}
							aria-invalid={errors.name ? true : undefined}
							{...register("name")}
						/>
						{errors.name ? (
							<p role="alert" className="text-sm text-destructive">
								{errors.name.message}
							</p>
						) : null}
					</div>
					<div className="flex flex-col gap-1.5">
						<Label htmlFor={`edit-ingredient-unit-${ingredient.id}`}>
							Unit label
						</Label>
						<Input
							id={`edit-ingredient-unit-${ingredient.id}`}
							aria-invalid={errors.unitLabel ? true : undefined}
							{...register("unitLabel")}
						/>
						{errors.unitLabel ? (
							<p role="alert" className="text-sm text-destructive">
								{errors.unitLabel.message}
							</p>
						) : null}
					</div>
					<div className="flex flex-col gap-1.5">
						<Label htmlFor={`edit-ingredient-price-${ingredient.id}`}>
							Price per unit ($)
						</Label>
						<Input
							id={`edit-ingredient-price-${ingredient.id}`}
							type="text"
							inputMode="decimal"
							aria-invalid={errors.priceDollars ? true : undefined}
							{...register("priceDollars")}
						/>
						{errors.priceDollars ? (
							<p role="alert" className="text-sm text-destructive">
								{errors.priceDollars.message}
							</p>
						) : null}
					</div>
					<div className="flex items-center gap-2">
						<Controller
							control={control}
							name="active"
							render={({ field }) => (
								<Switch
									id={`edit-ingredient-active-${ingredient.id}`}
									checked={field.value}
									onCheckedChange={field.onChange}
								/>
							)}
						/>
						<Label htmlFor={`edit-ingredient-active-${ingredient.id}`}>
							Active
						</Label>
					</div>
					{update.isError ? (
						<p role="alert" className="text-sm text-destructive">
							{problemMessage(update.error)}
						</p>
					) : null}
					<div className="flex gap-2">
						<Button type="submit" size="sm" disabled={update.isPending}>
							{update.isPending ? "Saving…" : "Save"}
						</Button>
						<Button
							type="button"
							size="sm"
							variant="ghost"
							onClick={onDone}
							disabled={update.isPending}
						>
							Cancel
						</Button>
					</div>
				</form>
			</CardContent>
		</Card>
	);
}
