import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { request } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { addDays, todayIsoDate } from "@/lib/dates";
import { problemMessage } from "@/lib/problemMessage";

type RecipeRead = components["schemas"]["RecipeRead"];
type BatchCreate = components["schemas"]["BatchCreate"];
type BatchRead = components["schemas"]["BatchRead"];

type BakeFormValues = {
	baked: string;
	expires: string;
	counts: number[];
};

function bakeSchema() {
	return z
		.object({
			baked: z.string().min(1, "Baked date is required"),
			expires: z.string().min(1, "Expiration date is required"),
			counts: z.array(
				z.number().int("Enter a whole number").min(0, "Enter zero or more"),
			),
		})
		.refine((values) => values.expires >= values.baked, {
			message: "Expiration must be on or after the baked date",
			path: ["expires"],
		})
		.refine((values) => values.counts.some((count) => count > 0), {
			message: "Enter a count greater than zero for at least one size",
			path: ["counts"],
		});
}

type BakeFormProps = {
	recipe: RecipeRead;
	onBaked: (batch: BatchRead) => void;
};

/**
 * Bake form for one recipe. One number input per size, prefilled from the
 * recipe's typical yield and always sent (the API skips a zero-count row).
 * Keyed by `recipe.id` from the parent so switching recipes remounts this
 * form with fresh defaults instead of syncing state through an effect.
 */
export function BakeForm({ recipe, onBaked }: BakeFormProps) {
	const queryClient = useQueryClient();
	const baked = todayIsoDate();
	const {
		register,
		handleSubmit,
		formState: { errors },
	} = useForm<BakeFormValues>({
		resolver: zodResolver(bakeSchema()),
		defaultValues: {
			baked,
			expires: addDays(baked, recipe.shelf_life_days),
			counts: recipe.sizes.map((size) => size.typical_yield_count),
		},
	});

	const bake = useMutation({
		mutationFn: (values: BakeFormValues) => {
			const body: BatchCreate = {
				recipe_id: recipe.id,
				baked: values.baked,
				expires: values.expires,
				counts: recipe.sizes.map((size, index) => ({
					size_id: size.id,
					count: values.counts[index] ?? 0,
				})),
			};
			return request<BatchRead>("POST", "/api/v1/batches", body);
		},
		onSuccess: (batch) => {
			void queryClient.invalidateQueries({ queryKey: ["stock"] });
			void queryClient.invalidateQueries({ queryKey: ["entries"] });
			onBaked(batch);
		},
	});

	const onSubmit = handleSubmit((values) => bake.mutate(values));

	return (
		<form onSubmit={onSubmit} className="flex flex-col gap-4">
			<div className="flex flex-col gap-1.5">
				<Label htmlFor="baked">Baked</Label>
				<Input
					id="baked"
					type="date"
					aria-invalid={errors.baked ? true : undefined}
					aria-describedby={errors.baked ? "baked-error" : undefined}
					{...register("baked")}
				/>
				{errors.baked ? (
					<p id="baked-error" role="alert" className="text-sm text-destructive">
						{errors.baked.message}
					</p>
				) : null}
			</div>
			<div className="flex flex-col gap-1.5">
				<Label htmlFor="expires">Expires</Label>
				<Input
					id="expires"
					type="date"
					aria-invalid={errors.expires ? true : undefined}
					aria-describedby={errors.expires ? "expires-error" : undefined}
					{...register("expires")}
				/>
				{errors.expires ? (
					<p
						id="expires-error"
						role="alert"
						className="text-sm text-destructive"
					>
						{errors.expires.message}
					</p>
				) : null}
			</div>
			<div className="flex flex-col gap-3">
				{recipe.sizes.map((size, index) => {
					const fieldError = errors.counts?.[index];
					const errorId = `count-${size.id}-error`;
					return (
						<div key={size.id} className="flex flex-col gap-1.5">
							<Label htmlFor={`count-${size.id}`}>{size.name}</Label>
							<Input
								id={`count-${size.id}`}
								type="number"
								inputMode="numeric"
								aria-invalid={fieldError ? true : undefined}
								aria-describedby={fieldError ? errorId : undefined}
								{...register(`counts.${index}`, { valueAsNumber: true })}
							/>
							{fieldError ? (
								<p
									id={errorId}
									role="alert"
									className="text-sm text-destructive"
								>
									{fieldError.message}
								</p>
							) : null}
						</div>
					);
				})}
				{errors.counts?.message ? (
					<p role="alert" className="text-sm text-destructive">
						{errors.counts.message}
					</p>
				) : null}
			</div>
			{bake.isError ? (
				<p role="alert" className="text-sm text-destructive">
					{problemMessage(bake.error)}
				</p>
			) : null}
			<Button type="submit" disabled={bake.isPending}>
				{bake.isPending ? "Recording bake…" : "Record bake"}
			</Button>
		</form>
	);
}
