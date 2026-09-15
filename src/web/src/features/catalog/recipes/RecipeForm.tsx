import { zodResolver } from "@hookform/resolvers/zod";
import { Controller, useFieldArray, useForm } from "react-hook-form";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { formatCents } from "@/lib/money";
import { problemMessage } from "@/lib/problemMessage";
import { type RecipeFormValues, recipeFormSchema } from "./recipeFormValues";

type IngredientRead = components["schemas"]["IngredientRead"];

type RecipeFormProps = {
	mode: "create" | "edit";
	defaultValues: RecipeFormValues;
	ingredients: IngredientRead[];
	/** Existing size id -> current `estimated_unit_cost_cents`; empty for a brand-new recipe. */
	estimatedCostsBySizeId: Map<number, number>;
	onSubmit: (values: RecipeFormValues) => void;
	submitting: boolean;
	submitError: unknown;
	submitLabel: string;
};

/**
 * Shared create/edit recipe form: name, shelf life, ingredient lines, and
 * sizes. Non-negotiable 3 stays server-side — this form never lets the user
 * choose a batch, only recipe-level facts. In edit mode, existing lines and
 * sizes have no remove control (`docs` "no delete actions of any kind");
 * only newly added, unsaved rows in create mode can be removed, since
 * nothing has been persisted yet.
 */
export function RecipeForm({
	mode,
	defaultValues,
	ingredients,
	estimatedCostsBySizeId,
	onSubmit,
	submitting,
	submitError,
	submitLabel,
}: RecipeFormProps) {
	const {
		register,
		handleSubmit,
		control,
		watch,
		formState: { errors },
	} = useForm<RecipeFormValues>({
		resolver: zodResolver(recipeFormSchema),
		defaultValues,
	});

	const linesArray = useFieldArray({ control, name: "lines" });
	const sizesArray = useFieldArray({ control, name: "sizes" });
	const lineValues = watch("lines");
	const sizeValues = watch("sizes");

	const onValid = handleSubmit((values) => onSubmit(values));

	return (
		<form onSubmit={onValid} className="flex flex-col gap-6">
			<div className="flex flex-col gap-1.5">
				<Label htmlFor="recipe-name">Name</Label>
				<Input
					id="recipe-name"
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
				<Label htmlFor="recipe-shelf-life">Shelf life (days)</Label>
				<Input
					id="recipe-shelf-life"
					type="number"
					inputMode="numeric"
					className="w-24"
					aria-invalid={errors.shelfLifeDays ? true : undefined}
					{...register("shelfLifeDays", { valueAsNumber: true })}
				/>
				{errors.shelfLifeDays ? (
					<p role="alert" className="text-sm text-destructive">
						{errors.shelfLifeDays.message}
					</p>
				) : null}
			</div>

			<section className="flex flex-col gap-3">
				<h2 className="text-lg font-semibold">Ingredient lines</h2>
				{errors.lines?.root?.message ? (
					<p role="alert" className="text-sm text-destructive">
						{errors.lines.root.message}
					</p>
				) : null}
				{linesArray.fields.length === 0 ? (
					<p className="text-sm text-muted-foreground">
						No ingredient lines yet.
					</p>
				) : null}
				{linesArray.fields.map((field, index) => {
					const currentIngredientId = lineValues[index]?.ingredientId;
					const options = ingredients.filter(
						(ingredient) =>
							ingredient.active || ingredient.id === currentIngredientId,
					);
					return (
						<Card key={field.id}>
							<CardContent className="flex flex-col gap-2">
								<div className="flex flex-col gap-1.5">
									<Label htmlFor={`line-ingredient-${field.id}`}>
										Ingredient
									</Label>
									<Controller
										control={control}
										name={`lines.${index}.ingredientId`}
										render={({ field: controllerField }) => (
											<Select
												value={
													controllerField.value
														? String(controllerField.value)
														: ""
												}
												onValueChange={(value) =>
													controllerField.onChange(Number(value))
												}
											>
												<SelectTrigger
													id={`line-ingredient-${field.id}`}
													className="w-full"
												>
													<SelectValue placeholder="Select ingredient" />
												</SelectTrigger>
												<SelectContent>
													{options.map((ingredient) => (
														<SelectItem
															key={ingredient.id}
															value={String(ingredient.id)}
														>
															{ingredient.name}
															{ingredient.active ? "" : " (inactive)"}
														</SelectItem>
													))}
												</SelectContent>
											</Select>
										)}
									/>
									{errors.lines?.[index]?.ingredientId ? (
										<p role="alert" className="text-sm text-destructive">
											{errors.lines[index]?.ingredientId?.message}
										</p>
									) : null}
								</div>
								<div className="flex flex-col gap-1.5">
									<Label htmlFor={`line-quantity-${field.id}`}>Quantity</Label>
									<Input
										id={`line-quantity-${field.id}`}
										type="number"
										inputMode="numeric"
										className="w-24"
										aria-invalid={
											errors.lines?.[index]?.quantity ? true : undefined
										}
										{...register(`lines.${index}.quantity`, {
											valueAsNumber: true,
										})}
									/>
									{errors.lines?.[index]?.quantity ? (
										<p role="alert" className="text-sm text-destructive">
											{errors.lines[index]?.quantity?.message}
										</p>
									) : null}
								</div>
								{mode === "create" ? (
									<Button
										type="button"
										size="sm"
										variant="ghost"
										className="self-start"
										aria-label={`Remove ingredient line ${index + 1}`}
										onClick={() => linesArray.remove(index)}
									>
										Remove line
									</Button>
								) : null}
							</CardContent>
						</Card>
					);
				})}
				<Button
					type="button"
					size="sm"
					variant="outline"
					className="self-start"
					onClick={() =>
						linesArray.append({
							ingredientId: 0,
							quantity: 0,
						})
					}
				>
					Add ingredient line
				</Button>
			</section>

			<section className="flex flex-col gap-3">
				<h2 className="text-lg font-semibold">Sizes</h2>
				{errors.sizes?.root?.message ? (
					<p role="alert" className="text-sm text-destructive">
						{errors.sizes.root.message}
					</p>
				) : null}
				{sizesArray.fields.map((field, index) => {
					const sizeId = sizeValues[index]?.id;
					const estimatedCents =
						sizeId !== undefined
							? estimatedCostsBySizeId.get(sizeId)
							: undefined;
					return (
						<Card key={field.id}>
							<CardContent className="flex flex-col gap-2">
								<div className="flex flex-col gap-1.5">
									<Label htmlFor={`size-name-${field.id}`}>Name</Label>
									<Input
										id={`size-name-${field.id}`}
										aria-invalid={
											errors.sizes?.[index]?.name ? true : undefined
										}
										{...register(`sizes.${index}.name`)}
									/>
									{errors.sizes?.[index]?.name ? (
										<p role="alert" className="text-sm text-destructive">
											{errors.sizes[index]?.name?.message}
										</p>
									) : null}
								</div>
								<div className="flex flex-col gap-1.5">
									<Label htmlFor={`size-weight-${field.id}`}>
										Portion weight (g)
									</Label>
									<Input
										id={`size-weight-${field.id}`}
										type="number"
										inputMode="numeric"
										className="w-24"
										aria-invalid={
											errors.sizes?.[index]?.portionWeightG ? true : undefined
										}
										{...register(`sizes.${index}.portionWeightG`, {
											valueAsNumber: true,
										})}
									/>
									{errors.sizes?.[index]?.portionWeightG ? (
										<p role="alert" className="text-sm text-destructive">
											{errors.sizes[index]?.portionWeightG?.message}
										</p>
									) : null}
								</div>
								<div className="flex flex-col gap-1.5">
									<Label htmlFor={`size-price-${field.id}`}>
										Sale price ($)
									</Label>
									<Input
										id={`size-price-${field.id}`}
										type="text"
										inputMode="decimal"
										aria-invalid={
											errors.sizes?.[index]?.priceDollars ? true : undefined
										}
										{...register(`sizes.${index}.priceDollars`)}
									/>
									{errors.sizes?.[index]?.priceDollars ? (
										<p role="alert" className="text-sm text-destructive">
											{errors.sizes[index]?.priceDollars?.message}
										</p>
									) : null}
								</div>
								<div className="flex flex-col gap-1.5">
									<Label htmlFor={`size-yield-${field.id}`}>
										Typical yield count
									</Label>
									<Input
										id={`size-yield-${field.id}`}
										type="number"
										inputMode="numeric"
										className="w-24"
										aria-invalid={
											errors.sizes?.[index]?.typicalYieldCount
												? true
												: undefined
										}
										{...register(`sizes.${index}.typicalYieldCount`, {
											valueAsNumber: true,
										})}
									/>
									{errors.sizes?.[index]?.typicalYieldCount ? (
										<p role="alert" className="text-sm text-destructive">
											{errors.sizes[index]?.typicalYieldCount?.message}
										</p>
									) : null}
								</div>
								{estimatedCents !== undefined ? (
									<p className="text-sm text-muted-foreground">
										Estimated unit cost: {formatCents(estimatedCents)}
									</p>
								) : null}
								{mode === "create" && sizesArray.fields.length > 1 ? (
									<Button
										type="button"
										size="sm"
										variant="ghost"
										className="self-start"
										aria-label={`Remove size ${index + 1}`}
										onClick={() => sizesArray.remove(index)}
									>
										Remove size
									</Button>
								) : null}
							</CardContent>
						</Card>
					);
				})}
				<Button
					type="button"
					size="sm"
					variant="outline"
					className="self-start"
					onClick={() =>
						sizesArray.append({
							name: "",
							portionWeightG: 1,
							priceDollars: "0",
							typicalYieldCount: 1,
						})
					}
				>
					Add size
				</Button>
			</section>

			{submitError ? (
				<p role="alert" className="text-sm text-destructive">
					{problemMessage(submitError)}
				</p>
			) : null}
			<Button type="submit" disabled={submitting} className="self-start">
				{submitting ? "Saving…" : submitLabel}
			</Button>
		</form>
	);
}
