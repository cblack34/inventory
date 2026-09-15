import type { ReactNode } from "react";
import { Link } from "react-router";

/** Top bar and nav shared by every authenticated screen. Mobile-first: usable at 375px. */
export function Layout({ children }: { children: ReactNode }) {
	return (
		<div className="flex min-h-screen flex-col">
			<header className="flex items-center justify-between border-b px-4 py-3">
				<span className="font-heading text-lg font-semibold">inventory</span>
				<nav>
					<Link to="/" className="text-sm font-medium">
						Home
					</Link>
					<Link to="/ingredients" className="text-sm font-medium">
						Ingredients
					</Link>
					<Link to="/recipes" className="text-sm font-medium">
						Recipes
					</Link>
					<Link to="/locations" className="text-sm font-medium">
						Locations
					</Link>
				</nav>
			</header>
			<main className="flex-1 px-4 py-4">{children}</main>
		</div>
	);
}
