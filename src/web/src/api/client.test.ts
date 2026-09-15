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
					instance: "/api/v1/session",
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
			expect(problem.instance).toBe("/api/v1/session");
			expect(problem.extensions).toEqual({ retry_after_seconds: 30 });
			return true;
		});
	});

	it("redirects to /login on a 401 from a non-session path", async () => {
		const assign = vi.fn();
		vi.stubGlobal("window", { location: { assign } });
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue(
				jsonResponse(401, {
					type: "urn:inventory:problem:unauthorized",
					title: "Unauthorized",
					status: 401,
					detail: "a valid session is required",
					instance: null,
				}),
			),
		);

		await expect(request("GET", "/api/v1/stock")).rejects.toBeInstanceOf(
			ProblemError,
		);
		expect(assign).toHaveBeenCalledWith("/login");
	});

	it("does not redirect on a 401 from the session path", async () => {
		const assign = vi.fn();
		vi.stubGlobal("window", { location: { assign } });
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue(
				jsonResponse(401, {
					type: "urn:inventory:problem:invalid-credentials",
					title: "Invalid Credentials",
					status: 401,
					detail: "incorrect password",
					instance: null,
				}),
			),
		);

		await expect(
			request("POST", "/api/v1/session", { password: "nope" }),
		).rejects.toBeInstanceOf(ProblemError);
		expect(assign).not.toHaveBeenCalled();
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
