import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { request } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { formatCents } from "@/lib/money";
import { problemMessage } from "@/lib/problemMessage";
import { BakeForm } from "./BakeForm";

type RecipeRead = components["schemas"]["RecipeRead"];
type BatchRead = components["schemas"]["BatchRead"];
type TodayResponse = components["schemas"]["TodayResponse"];

type BakedResult = {
	batch: BatchRead;
	recipe: RecipeRead;
};

/** `/bake`: pick a recipe, record a batch, then show the read-only result. */
export function BakePage() {
	const recipesQuery = useQuery({
		queryKey: ["recipes"],
		queryFn: () => request<RecipeRead[]>("GET", "/api/v1/recipes"),
	});
	// The bake form's `baked` prefill: the server's business date, not the
	// browser's clock (`docs/data-model.md`, "Expiration").
	const todayQuery = useQuery({
		queryKey: ["today"],
		queryFn: () => request<TodayResponse>("GET", "/api/v1/today"),
	});
	const [recipeId, setRecipeId] = useState<number | undefined>(undefined);
	const [result, setResult] = useState<BakedResult | undefined>(undefined);

	if (recipesQuery.isPending || todayQuery.isPending) {
		return <p>Loading recipes…</p>;
	}
	if (recipesQuery.isError && recipesQuery.data === undefined) {
		return <p role="alert">{problemMessage(recipesQuery.error)}</p>;
	}
	if (todayQuery.isError && todayQuery.data === undefined) {
		return <p role="alert">{problemMessage(todayQuery.error)}</p>;
	}

	const recipes = recipesQuery.data;
	const today = todayQuery.data.today;

	if (result) {
		return (
			<BatchResult
				batch={result.batch}
				recipe={result.recipe}
				onBakeAnother={() => setResult(undefined)}
			/>
		);
	}

	const firstRecipe = recipes[0];
	if (firstRecipe === undefined) {
		return <p className="text-sm text-muted-foreground">No recipes yet.</p>;
	}

	const selectedId = recipeId ?? firstRecipe.id;
	const recipe =
		recipes.find((candidate) => candidate.id === selectedId) ?? firstRecipe;

	return (
		<div className="flex flex-col gap-4">
			<h1 className="text-xl font-semibold">Bake</h1>
			<div className="flex flex-col gap-1.5">
				<Label htmlFor="recipe">Recipe</Label>
				<NativeSelect
					id="recipe"
					value={recipe.id}
					onChange={(event) => setRecipeId(Number(event.target.value))}
				>
					{recipes.map((candidate) => (
						<option key={candidate.id} value={candidate.id}>
							{candidate.name}
						</option>
					))}
				</NativeSelect>
			</div>
			<BakeForm
				key={recipe.id}
				recipe={recipe}
				today={today}
				onBaked={(batch) => setResult({ batch, recipe })}
			/>
		</div>
	);
}

/**
 * Read-only detail of the batch just recorded: total cost and per-size unit
 * cost from the `BatchRead` the bake POST already returned. Never shows the
 * batch id (non-negotiable 3 keeps batch identity out of every screen).
 */
function BatchResult({
	batch,
	recipe,
	onBakeAnother,
}: {
	batch: BatchRead;
	recipe: RecipeRead;
	onBakeAnother: () => void;
}) {
	const sizeNames = new Map(recipe.sizes.map((size) => [size.id, size.name]));

	return (
		<Card>
			<CardHeader>
				<CardTitle>Batch recorded</CardTitle>
			</CardHeader>
			<CardContent className="flex flex-col gap-3">
				<p className="text-sm text-muted-foreground">{recipe.name}</p>
				<p className="font-medium">
					Total cost {formatCents(batch.total_cost_cents)}
				</p>
				<ul className="flex flex-col gap-1">
					{batch.sizes.map((size) => (
						<li key={size.size_id} className="text-sm">
							{sizeNames.get(size.size_id) ?? "Size"}: {size.count_made} at{" "}
							{formatCents(size.unit_cost_cents)} each
						</li>
					))}
				</ul>
				<div className="flex gap-2">
					<Button type="button" onClick={onBakeAnother}>
						Bake another
					</Button>
					<Button type="button" variant="outline" asChild>
						<Link to="/">Home</Link>
					</Button>
				</div>
			</CardContent>
		</Card>
	);
}
