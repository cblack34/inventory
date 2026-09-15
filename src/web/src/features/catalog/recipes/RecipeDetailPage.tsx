import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router";
import { request } from "@/api/client";
import type { components } from "@/api/types";
import { problemMessage } from "@/lib/problemMessage";
import { RecipeForm } from "./RecipeForm";
import {
	type RecipeFormValues,
	recipeToFormValues,
	toRecipePatch,
} from "./recipeFormValues";

type IngredientRead = components["schemas"]["IngredientRead"];
type RecipeRead = components["schemas"]["RecipeRead"];

/** Parses the `:recipeId` route param, or `null` if it is missing or not a positive integer. */
function parseRecipeId(param: string | undefined): number | null {
	if (!param) {
		return null;
	}
	const id = Number.parseInt(param, 10);
	return Number.isInteger(id) && id > 0 ? id : null;
}

/**
 * View and edit an existing recipe. Sizes show `estimated_unit_cost_cents`
 * from the last fetch; TanStack Query's default zero stale time means
 * revisiting this screen after an ingredient price change refetches and
 * shows the updated estimate, with no cross-query invalidation needed.
 */
export function RecipeDetailPage() {
	const { recipeId: recipeIdParam } = useParams();
	const recipeId = parseRecipeId(recipeIdParam);

	const recipeQuery = useQuery({
		queryKey: ["recipes", recipeId],
		queryFn: () => request<RecipeRead>("GET", `/api/v1/recipes/${recipeId}`),
		enabled: recipeId !== null,
	});
	const ingredientsQuery = useQuery({
		queryKey: ["ingredients"],
		queryFn: () => request<IngredientRead[]>("GET", "/api/v1/ingredients"),
	});
	const queryClient = useQueryClient();

	const update = useMutation({
		mutationFn: (values: RecipeFormValues) => {
			if (recipeId === null) {
				throw new Error("Missing recipe id");
			}
			return request<RecipeRead>(
				"PATCH",
				`/api/v1/recipes/${recipeId}`,
				toRecipePatch(values),
			);
		},
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: ["recipes"] });
		},
	});

	if (recipeId === null) {
		return <p role="alert">Recipe not found.</p>;
	}
	if (recipeQuery.isPending || ingredientsQuery.isPending) {
		return <p>Loading recipe…</p>;
	}
	if (recipeQuery.isError) {
		return <p role="alert">{problemMessage(recipeQuery.error)}</p>;
	}
	if (ingredientsQuery.isError) {
		return <p role="alert">{problemMessage(ingredientsQuery.error)}</p>;
	}

	const recipe = recipeQuery.data;
	const estimatedCostsBySizeId = new Map(
		recipe.sizes.map((size) => [size.id, size.estimated_unit_cost_cents]),
	);

	return (
		<div className="flex flex-col gap-6">
			<h1 className="text-xl font-semibold">{recipe.name}</h1>
			<RecipeForm
				// Keyed by id only (not by content): a background refetch —
				// e.g. on window focus — must not remount the form and wipe
				// in-progress edits. ponytail: a size added and saved in this
				// same session won't show its estimated cost until the next
				// visit to this page, since the form's field-array state
				// keeps the in-progress `id: undefined` until then; simplest
				// fix given the "no remount mid-edit" constraint above.
				key={recipe.id}
				mode="edit"
				defaultValues={recipeToFormValues(recipe)}
				ingredients={ingredientsQuery.data}
				estimatedCostsBySizeId={estimatedCostsBySizeId}
				onSubmit={(values) => update.mutate(values)}
				submitting={update.isPending}
				submitError={update.isError ? update.error : null}
				submitLabel="Save recipe"
			/>
		</div>
	);
}
