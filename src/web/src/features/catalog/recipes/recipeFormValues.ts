import { z } from "zod";
import type { components } from "@/api/types";
import { centsToDollarsInput, parseDollarsToCents } from "@/lib/dollars";

type RecipeCreate = components["schemas"]["RecipeCreate"];
type RecipePatch = components["schemas"]["RecipePatch"];
type RecipeRead = components["schemas"]["RecipeRead"];

/** Parses a dollars string already validated by `sizeSchema`, never `null` in practice. */
export function centsOrThrow(dollars: string): number {
	const cents = parseDollarsToCents(dollars);
	if (cents === null) {
		throw new Error(`Invalid dollars value after validation: ${dollars}`);
	}
	return cents;
}

const dollarsSchema = z
	.string()
	.min(1, "Required")
	.refine((value) => parseDollarsToCents(value) !== null, {
		message: "Enter a dollar amount like 1.23",
	})
	.refine((value) => (parseDollarsToCents(value) ?? -1) >= 0, {
		message: "Must be zero or more",
	});

const lineSchema = z.object({
	ingredientId: z.number().int().positive("Choose an ingredient"),
	quantity: z.number().int("Whole numbers only").min(0, "Must be zero or more"),
});

const sizeSchema = z.object({
	// Present for a size loaded from an existing recipe; absent for a size
	// added in this session, so the submit step knows whether to send it as
	// a `SizePatchItem` update (`id` present) or a create (`id` omitted —
	// never sent as `null`).
	id: z.number().int().positive().optional(),
	name: z.string().min(1, "Required"),
	portionWeightG: z
		.number()
		.int("Whole numbers only")
		.positive("Must be greater than zero"),
	priceDollars: dollarsSchema,
	typicalYieldCount: z
		.number()
		.int("Whole numbers only")
		.min(0, "Must be zero or more"),
});

/**
 * Recipe form schema. Mirrors the two acceptance-level constraints the API
 * enforces (`docs/acceptance.md`, "Ingredients and recipes"), for immediate
 * feedback; the server remains the authority and its Problem `detail` is
 * shown for anything this misses.
 */
export const recipeFormSchema = z.object({
	name: z.string().min(1, "Required"),
	shelfLifeDays: z
		.number()
		.int("Whole numbers only")
		.min(0, "Must be zero or more"),
	lines: z
		.array(lineSchema)
		.refine(
			(lines) =>
				new Set(lines.map((line) => line.ingredientId)).size === lines.length,
			{ message: "Each ingredient can only appear once" },
		),
	sizes: z
		.array(sizeSchema)
		.min(1, "Add at least one size")
		.refine(
			(sizes) =>
				new Set(sizes.map((size) => size.name.trim().toLowerCase())).size ===
				sizes.length,
			{ message: "Size names must be unique" },
		)
		.refine(
			(sizes) =>
				sizes.reduce(
					(total, size) => total + size.portionWeightG * size.typicalYieldCount,
					0,
				) > 0,
			{ message: "Total typical yield weight must be greater than zero" },
		),
});

export type RecipeFormValues = z.infer<typeof recipeFormSchema>;

/** Default values for a brand-new recipe: one blank, editable size row. */
export function newRecipeDefaultValues(): RecipeFormValues {
	return {
		name: "",
		shelfLifeDays: 0,
		lines: [],
		sizes: [
			{
				name: "",
				portionWeightG: 1,
				priceDollars: "0",
				typicalYieldCount: 1,
			},
		],
	};
}

/** Default values from a recipe already on the server, for the edit form. */
export function recipeToFormValues(recipe: RecipeRead): RecipeFormValues {
	return {
		name: recipe.name,
		shelfLifeDays: recipe.shelf_life_days,
		lines: recipe.lines.map((line) => ({
			ingredientId: line.ingredient_id,
			quantity: line.quantity,
		})),
		sizes: recipe.sizes.map((size) => ({
			id: size.id,
			name: size.name,
			portionWeightG: size.portion_weight_g,
			priceDollars: centsToDollarsInput(size.price_cents),
			typicalYieldCount: size.typical_yield_count,
		})),
	};
}

export function toRecipeCreate(values: RecipeFormValues): RecipeCreate {
	return {
		name: values.name,
		shelf_life_days: values.shelfLifeDays,
		lines: values.lines.map((line) => ({
			ingredient_id: line.ingredientId,
			quantity: line.quantity,
		})),
		sizes: values.sizes.map((size) => ({
			name: size.name,
			portion_weight_g: size.portionWeightG,
			price_cents: centsOrThrow(size.priceDollars),
			typical_yield_count: size.typicalYieldCount,
		})),
	};
}

export function toRecipePatch(values: RecipeFormValues): RecipePatch {
	return {
		name: values.name,
		shelf_life_days: values.shelfLifeDays,
		lines: values.lines.map((line) => ({
			ingredient_id: line.ingredientId,
			quantity: line.quantity,
		})),
		sizes: values.sizes.map((size) => {
			const priceCents = centsOrThrow(size.priceDollars);
			return size.id === undefined
				? {
						name: size.name,
						portion_weight_g: size.portionWeightG,
						price_cents: priceCents,
						typical_yield_count: size.typicalYieldCount,
					}
				: {
						id: size.id,
						name: size.name,
						portion_weight_g: size.portionWeightG,
						price_cents: priceCents,
						typical_yield_count: size.typicalYieldCount,
					};
		}),
	};
}
