import { afterEach, describe, expect, it, vi } from "vitest";
import { ProblemError, request } from "./client";

function jsonResponse(status: number, body: unknown) {
	return new Response(JSON.stringify(body), {
		status,
		headers: { "content-type": "application/problem+json" },
	});
}

afterEach(() => {
	vi.unstubAllGlobals();
});

describe("request", () => {
	it("parses a 422 problem response into a ProblemError", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue(
				jsonResponse(422, {
					type: "https://example.com/problems/validation",
					title: "Unprocessable Content",
					status: 422,
					detail: "password must not be empty",
					instance: null,
					retry_after_seconds: 30,
				}),
			),
		);

		await expect(
			request("POST", "/api/v1/session", { password: "" }),
		).rejects.toSatisfy((error: unknown) => {
			expect(error).toBeInstanceOf(ProblemError);
			const problem = error as ProblemError;
			expect(problem.status).toBe(422);
			expect(problem.detail).toBe("password must not be empty");
			expect(problem.extensions).toEqual({ retry_after_seconds: 30 });
			return true;
		});
	});

	it("resolves a 204 response to undefined", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue(new Response(null, { status: 204 })),
		);

		await expect(
			request("POST", "/api/v1/session", { password: "pw" }),
		).resolves.toBeUndefined();
	});
});
