import { ProblemError } from "@/api/client";

/** User-facing message for a failed mutation: the Problem `detail` when we have one. */
export function problemMessage(error: unknown): string {
	if (error instanceof ProblemError) {
		return error.detail ?? error.title;
	}
	return "Something went wrong. Try again.";
}
