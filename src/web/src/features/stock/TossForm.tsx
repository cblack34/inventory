import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { request } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { problemMessage } from "@/lib/problemMessage";

type MovementCreate = components["schemas"]["MovementCreate"];
type EntryRead = components["schemas"]["EntryRead"];

type TossFormValues = {
	quantity: number;
};

function tossSchema(onHand: number) {
	return z.object({
		quantity: z
			.number()
			.int("Enter a whole number")
			.positive("Enter a number greater than zero")
			.max(onHand, `Only ${onHand} on hand`),
	});
}

type TossFormProps = {
	sizeId: number;
	onHand: number;
	kitchenLocationId: number;
	wasteLocationId: number;
	onCancel: () => void;
};

/**
 * Inline toss form for one kitchen size row. Takes only a size and a count —
 * never a batch id — so FIFO selection stays entirely server-side
 * (non-negotiable 3).
 */
export function TossForm({
	sizeId,
	onHand,
	kitchenLocationId,
	wasteLocationId,
	onCancel,
}: TossFormProps) {
	const queryClient = useQueryClient();
	const {
		register,
		handleSubmit,
		formState: { errors },
	} = useForm<TossFormValues>({
		resolver: zodResolver(tossSchema(onHand)),
		defaultValues: { quantity: 1 },
	});

	const toss = useMutation({
		mutationFn: (values: TossFormValues) => {
			const body: MovementCreate = {
				from_location_id: kitchenLocationId,
				to_location_id: wasteLocationId,
				size_id: sizeId,
				quantity: values.quantity,
			};
			return request<EntryRead>("POST", "/api/v1/movements", body);
		},
		// Awaited so the form (and its disabled submit) stays up until the
		// stock row shows the new on-hand; closing early would let a second
		// toss be entered against a stale count.
		onSuccess: async () => {
			await Promise.all([
				queryClient.invalidateQueries({ queryKey: ["stock"] }),
				queryClient.invalidateQueries({ queryKey: ["entries"] }),
			]);
			onCancel();
		},
	});

	const onSubmit = handleSubmit((values) => toss.mutate(values));

	return (
		<form
			onSubmit={onSubmit}
			className="mt-2 flex flex-col gap-2 border-t pt-2"
		>
			<div className="flex items-center gap-2">
				<Input
					type="number"
					inputMode="numeric"
					aria-label="Quantity to toss"
					className="w-16"
					{...register("quantity", { valueAsNumber: true })}
				/>
				<Button type="submit" size="sm" disabled={toss.isPending}>
					{toss.isPending ? "Tossing…" : "Confirm toss"}
				</Button>
				<Button
					type="button"
					size="sm"
					variant="ghost"
					onClick={onCancel}
					disabled={toss.isPending}
				>
					Cancel
				</Button>
			</div>
			{errors.quantity ? (
				<p role="alert" className="text-sm text-destructive">
					{errors.quantity.message}
				</p>
			) : null}
			{toss.isError ? (
				<p role="alert" className="text-sm text-destructive">
					{problemMessage(toss.error)}
				</p>
			) : null}
		</form>
	);
}
