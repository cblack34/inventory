import { Route, Routes } from "react-router";
import { Layout } from "@/components/Layout";
import { BakePage } from "@/features/bake/BakePage";
import { MovePage } from "@/features/movements/MovePage";
import { NewVisitPage } from "@/features/visits/NewVisitPage";
import { VisitDetailPage } from "@/features/visits/VisitDetailPage";
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
				path="/bake"
				element={
					<Layout>
						<BakePage />
					</Layout>
				}
			/>
			<Route
				path="/move"
				element={
					<Layout>
						<MovePage />
					</Layout>
				}
			/>
			<Route
				path="/visits/new"
				element={
					<Layout>
						<NewVisitPage />
					</Layout>
				}
			/>
			<Route
				path="/visits/:entryId"
				element={
					<Layout>
						<VisitDetailPage />
					</Layout>
				}
			/>
		</Routes>
	);
}

export default App;
