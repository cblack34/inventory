import type { components } from "./types";

type Problem = components["schemas"]["Problem"];

/** RFC 9457 Problem Details error, thrown by `request` on any non-2xx response. */
export class ProblemError extends Error {
	readonly type: string;
	readonly title: string;
	readonly status: number;
	readonly detail: string | null;
	readonly instance: string | null;
	readonly extensions: Record<string, unknown>;

	constructor(problem: Problem) {
		super(problem.detail ?? problem.title);
		this.name = "ProblemError";
		this.type = problem.type;
		this.title = problem.title;
		this.status = problem.status;
		this.detail = problem.detail;
		this.instance = problem.instance;

		const knownKeys = new Set([
			"type",
			"title",
			"status",
			"detail",
			"instance",
		]);
		this.extensions = Object.fromEntries(
			Object.entries(problem).filter(([key]) => !knownKeys.has(key)),
		);
	}
}

// ponytail: the login path is exempt from the 401-redirect because a wrong
// password on /login legitimately answers 401 and must not bounce the user
// back to /login (they're already there).
const SESSION_PATH = "/api/v1/session";

function isProblem(value: unknown): value is Problem {
	return (
		typeof value === "object" &&
		value !== null &&
		"type" in value &&
		"title" in value &&
		"status" in value
	);
}

/**
 * Typed fetch wrapper. Sends and expects JSON, throws `ProblemError` on any
 * non-2xx response, and returns `undefined` for a 204. On a 401 from any path
 * other than `/api/v1/session` it redirects the browser to `/login` before
 * throwing, since the session has expired or was never established.
 */
export async function request<T>(
	method: "GET" | "POST" | "PATCH" | "DELETE",
	path: string,
	body?: unknown,
): Promise<T> {
	const response = await fetch(path, {
		method,
		headers: { "content-type": "application/json" },
		credentials: "same-origin",
		body: body === undefined ? undefined : JSON.stringify(body),
	});

	if (response.status === 204) {
		return undefined as T;
	}

	if (!response.ok) {
		if (response.status === 401 && path !== SESSION_PATH) {
			window.location.assign("/login");
		}

		let payload: unknown;
		try {
			payload = await response.json();
		} catch {
			payload = undefined;
		}

		const problem: Problem = isProblem(payload)
			? payload
			: {
					type: "about:blank",
					title: response.statusText || "Request failed",
					status: response.status,
					detail: null,
					instance: null,
				};

		throw new ProblemError(problem);
	}

	return (await response.json()) as T;
}
