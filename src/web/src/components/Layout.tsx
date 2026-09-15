import type { ReactNode } from "react";
import { Link } from "react-router";

/**
 * Top bar and nav shared by every authenticated screen. Mobile-first: the
 * seven links wrap onto a second row at 375 px instead of overflowing.
 */
export function Layout({ children }: { children: ReactNode }) {
	return (
		<div className="flex min-h-screen flex-col">
			<header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b px-4 py-3">
				<span className="font-heading text-lg font-semibold">inventory</span>
				<nav className="flex flex-wrap gap-x-4 gap-y-1">
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
					<Link to="/bake" className="text-sm font-medium">
						Bake
					</Link>
					<Link to="/move" className="text-sm font-medium">
						Move
					</Link>
					<Link to="/visits/new" className="text-sm font-medium">
						Visit
					</Link>
				</nav>
			</header>
			<main className="flex-1 px-4 py-4">{children}</main>
		</div>
	);
}
