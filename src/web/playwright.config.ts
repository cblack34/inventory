import { defineConfig, devices } from "@playwright/test";

// Exactly one smoke test (docs/tech-stack.md): log in, load home. The
// server under test is the real API, not a mock; `make e2e` migrates a
// scratch SQLite file before this config's `webServer` starts
// `python -m inventory` against it (that command never migrates itself).
export default defineConfig({
	testDir: "e2e",
	fullyParallel: false,
	reporter: "list",
	use: {
		baseURL: "http://localhost:8000",
	},
	projects: [
		{
			name: "chromium",
			use: {
				...devices["Desktop Chrome"],
				viewport: { width: 375, height: 812 },
			},
		},
	],
	webServer: {
		command: "uv run python -m inventory",
		url: "http://localhost:8000/api/v1/health",
		reuseExistingServer: false,
		cwd: "../..",
	},
});
