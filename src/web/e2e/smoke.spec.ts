import { expect, test } from "@playwright/test";

function requiredEnv(name: string): string {
	const value = process.env[name];
	if (!value) {
		throw new Error(`missing required env var: ${name}`);
	}
	return value;
}

// The one Playwright smoke test (docs/tech-stack.md): an unauthenticated
// visit redirects to /login, logging in lands back on / with the home
// screen rendered.
test("log in and load home", async ({ page }) => {
	await page.goto("/");
	await expect(page).toHaveURL("/login");

	await page.getByLabel("Password").fill(requiredEnv("SHARED_PASSWORD"));
	await page.getByRole("button", { name: "Log in" }).click();

	await expect(page).toHaveURL("/");
	await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();
});
