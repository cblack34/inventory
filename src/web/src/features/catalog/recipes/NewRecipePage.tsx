import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { request } from "@/api/client";
import type { components } from "@/api/types";
import { problemMessage } from "@/lib/problemMessage";
import { RecipeForm } from "./RecipeForm";
import {
	newRecipeDefaultValues,
	type RecipeFormValues,
	toRecipeCreate,
} from "./recipeFormValues";

type IngredientRead = components["schemas"]["IngredientRead"];
type RecipeRead = components["schemas"]["RecipeRead"];

/** Create a recipe: name, shelf life, ingredient lines, and one or more sizes. */
export function NewRecipePage() {
	const navigate = useNavigate();
	const queryClient = useQueryClient();
	const ingredientsQuery = useQuery({
		queryKey: ["ingredients"],
		queryFn: () => request<IngredientRead[]>("GET", "/api/v1/ingredients"),
	});

	const create = useMutation({
		mutationFn: (values: RecipeFormValues) =>
			request<RecipeRead>("POST", "/api/v1/recipes", toRecipeCreate(values)),
		onSuccess: (recipe) => {
			void queryClient.invalidateQueries({ queryKey: ["recipes"] });
			navigate(`/recipes/${recipe.id}`);
		},
	});

	if (ingredientsQuery.isPending) {
		return <p>Loading…</p>;
	}
	if (ingredientsQuery.isError) {
		return <p role="alert">{problemMessage(ingredientsQuery.error)}</p>;
	}

	return (
		<div className="flex flex-col gap-6">
			<h1 className="text-xl font-semibold">New recipe</h1>
			<RecipeForm
				mode="create"
				defaultValues={newRecipeDefaultValues()}
				ingredients={ingredientsQuery.data}
				estimatedCostsBySizeId={new Map()}
				onSubmit={(values) => create.mutate(values)}
				submitting={create.isPending}
				submitError={create.isError ? create.error : null}
				submitLabel="Create recipe"
			/>
		</div>
	);
}
