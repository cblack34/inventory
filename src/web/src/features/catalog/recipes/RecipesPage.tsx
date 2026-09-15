import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { request } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { problemMessage } from "@/lib/problemMessage";

type RecipeRead = components["schemas"]["RecipeRead"];

/** Recipes: list with a link to each detail/edit screen, and to create one. */
export function RecipesPage() {
	const recipesQuery = useQuery({
		queryKey: ["recipes"],
		queryFn: () => request<RecipeRead[]>("GET", "/api/v1/recipes"),
	});

	return (
		<div className="flex flex-col gap-6">
			<div className="flex items-center justify-between gap-2">
				<h1 className="text-xl font-semibold">Recipes</h1>
				<Button asChild size="sm">
					<Link to="/recipes/new">New recipe</Link>
				</Button>
			</div>
			{recipesQuery.isPending ? <p>Loading recipes…</p> : null}
			{recipesQuery.isError ? (
				<p role="alert">{problemMessage(recipesQuery.error)}</p>
			) : null}
			{recipesQuery.data ? (
				<section className="flex flex-col gap-3">
					{recipesQuery.data.length === 0 ? (
						<p className="text-sm text-muted-foreground">No recipes yet.</p>
					) : (
						recipesQuery.data.map((recipe) => (
							<Card key={recipe.id}>
								<CardHeader>
									<CardTitle asChild>
										<Link
											to={`/recipes/${recipe.id}`}
											className="min-w-0 break-words"
										>
											{recipe.name}
										</Link>
									</CardTitle>
								</CardHeader>
								<CardContent>
									<p className="text-sm text-muted-foreground">
										Shelf life {recipe.shelf_life_days} days ·{" "}
										{recipe.sizes.length}{" "}
										{recipe.sizes.length === 1 ? "size" : "sizes"}
									</p>
								</CardContent>
							</Card>
						))
					)}
				</section>
			) : null}
		</div>
	);
}
