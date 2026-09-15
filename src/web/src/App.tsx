import { Route, Routes } from "react-router";
import { Layout } from "@/components/Layout";
import { IngredientsPage } from "@/features/catalog/IngredientsPage";
import { LocationsPage } from "@/features/catalog/LocationsPage";
import { NewRecipePage } from "@/features/catalog/recipes/NewRecipePage";
import { RecipeDetailPage } from "@/features/catalog/recipes/RecipeDetailPage";
import { RecipesPage } from "@/features/catalog/recipes/RecipesPage";
import { HomePage } from "@/pages/HomePage";
import { LoginPage } from "@/pages/LoginPage";

function App() {
	return (
		<Routes>
			<Route path="/login" element={<LoginPage />} />
			<Route
				path="/"
				element={
					<Layout>
						<HomePage />
					</Layout>
				}
			/>
			<Route
				path="/ingredients"
				element={
					<Layout>
						<IngredientsPage />
					</Layout>
				}
			/>
			<Route
				path="/recipes"
				element={
					<Layout>
						<RecipesPage />
					</Layout>
				}
			/>
			<Route
				path="/recipes/new"
				element={
					<Layout>
						<NewRecipePage />
					</Layout>
				}
			/>
			<Route
				path="/recipes/:recipeId"
				element={
					<Layout>
						<RecipeDetailPage />
					</Layout>
				}
			/>
			<Route
				path="/locations"
				element={
					<Layout>
						<LocationsPage />
					</Layout>
				}
			/>
		</Routes>
	);
}

export default App;
