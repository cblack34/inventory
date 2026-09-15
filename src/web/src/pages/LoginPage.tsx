import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router";
import { z } from "zod";
import { ProblemError, request } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const loginSchema = z.object({
	password: z.string().min(1, "Password is required"),
});

type LoginForm = z.infer<typeof loginSchema>;

export function LoginPage() {
	const navigate = useNavigate();
	const {
		register,
		handleSubmit,
		formState: { errors },
	} = useForm<LoginForm>({ resolver: zodResolver(loginSchema) });

	const login = useMutation({
		mutationFn: (values: LoginForm) =>
			request<undefined>("POST", "/api/v1/session", values),
		onSuccess: () => navigate("/"),
	});

	const onSubmit = handleSubmit((values) => login.mutate(values));

	return (
		<div className="flex min-h-screen items-center justify-center px-4">
			<Card className="w-full max-w-sm">
				<CardHeader>
					<CardTitle asChild>
						<h1>Log in</h1>
					</CardTitle>
				</CardHeader>
				<CardContent>
					<form onSubmit={onSubmit} className="flex flex-col gap-4">
						<div className="flex flex-col gap-1.5">
							<Label htmlFor="password">Password</Label>
							<Input
								id="password"
								type="password"
								autoComplete="current-password"
								aria-invalid={errors.password ? true : undefined}
								aria-describedby={
									errors.password ? "password-error" : undefined
								}
								{...register("password")}
							/>
							{errors.password ? (
								<p
									id="password-error"
									role="alert"
									className="text-sm text-destructive"
								>
									{errors.password.message}
								</p>
							) : null}
						</div>
						{login.isError ? (
							<p role="alert" className="text-sm text-destructive">
								{loginErrorMessage(login.error)}
							</p>
						) : null}
						<Button type="submit" disabled={login.isPending}>
							{login.isPending ? "Logging in…" : "Log in"}
						</Button>
					</form>
				</CardContent>
			</Card>
		</div>
	);
}

function loginErrorMessage(error: unknown): string {
	if (!(error instanceof ProblemError)) {
		return "Something went wrong. Try again.";
	}

	if (error.status === 429) {
		const retryAfterSeconds = error.extensions.retry_after_seconds;
		return typeof retryAfterSeconds === "number"
			? `${error.detail ?? "Too many attempts."} Try again in ${retryAfterSeconds}s.`
			: (error.detail ?? "Too many attempts.");
	}

	return error.detail ?? error.title;
}
