import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router";
import { request } from "@/api/client";
import type { components } from "@/api/types";
import { problemMessage } from "@/lib/problemMessage";
import { parseRouteId } from "@/lib/routeId";
import { RecipeForm } from "./RecipeForm";
import {
	type RecipeFormValues,
	recipeToFormValues,
	toRecipePatch,
} from "./recipeFormValues";

type IngredientRead = components["schemas"]["IngredientRead"];
type RecipeRead = components["schemas"]["RecipeRead"];

/**
 * View and edit an existing recipe. Sizes show `estimated_unit_cost_cents`
 * from the last fetch; TanStack Query's default zero stale time means
 * revisiting this screen after an ingredient price change refetches and
 * shows the updated estimate, with no cross-query invalidation needed.
 */
export function RecipeDetailPage() {
	const { recipeId: recipeIdParam } = useParams();
	const recipeId = parseRouteId(recipeIdParam);

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
	// Bumped only on a successful save, to force the form below to remount
	// from the fresh server data (see the `key` comment on `RecipeForm`).
	const [saveCount, setSaveCount] = useState(0);

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
		onSuccess: (data) => {
			queryClient.setQueryData(["recipes", recipeId], data);
			void queryClient.invalidateQueries({ queryKey: ["recipes"] });
			setSaveCount((count) => count + 1);
		},
	});

	if (recipeId === null) {
		return <p role="alert">Recipe not found.</p>;
	}
	if (recipeQuery.isPending || ingredientsQuery.isPending) {
		return <p>Loading recipe…</p>;
	}
	if (recipeQuery.isError && recipeQuery.data === undefined) {
		return <p role="alert">{problemMessage(recipeQuery.error)}</p>;
	}
	if (ingredientsQuery.isError && ingredientsQuery.data === undefined) {
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
				// Keyed by id and save count, not by content: a background
				// refetch — e.g. on window focus — must not remount the form
				// and wipe in-progress edits, so `saveCount` only advances
				// after a successful save. That remount re-derives
				// `defaultValues` from the just-returned `RecipeRead`, so a
				// size added in this same session picks up its
				// server-assigned id and estimated cost immediately instead
				// of waiting for the next visit to this page.
				key={`${recipe.id}:${saveCount}`}
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
