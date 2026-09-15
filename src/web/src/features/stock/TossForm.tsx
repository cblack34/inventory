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
	/** Recipe and size, so every control in this row is named for screen readers. */
	label: string;
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
	label,
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
		// The POST already committed the movement, so close the form as soon
		// as it succeeds — a retryable form over a committed toss is how a
		// second Kitchen→Waste movement gets appended for one user action.
		// Invalidations are fired without `throwOnError`: a refetch failure
		// surfaces as StockSection's/HistorySection's own query error state,
		// not as a reason to keep this form open.
		onSuccess: () => {
			onCancel();
			void queryClient.invalidateQueries({ queryKey: ["stock"] });
			void queryClient.invalidateQueries({ queryKey: ["entries"] });
		},
	});

	const onSubmit = handleSubmit((values) => toss.mutate(values));
	const errorId = `toss-quantity-error-${sizeId}`;

	return (
		<form
			aria-label={`Toss ${label}`}
			onSubmit={onSubmit}
			className="mt-2 flex flex-col gap-2 border-t pt-2"
		>
			<div className="flex items-center gap-2">
				<Input
					type="number"
					inputMode="numeric"
					aria-label={`Quantity to toss of ${label}`}
					aria-invalid={errors.quantity ? true : undefined}
					aria-describedby={errors.quantity ? errorId : undefined}
					className="w-16"
					{...register("quantity", { valueAsNumber: true })}
				/>
				<Button
					type="submit"
					size="sm"
					aria-label={`Confirm toss of ${label}`}
					disabled={toss.isPending}
				>
					{toss.isPending ? "Tossing…" : "Confirm toss"}
				</Button>
				<Button
					type="button"
					size="sm"
					variant="ghost"
					aria-label={`Cancel toss of ${label}`}
					onClick={onCancel}
					disabled={toss.isPending}
				>
					Cancel
				</Button>
			</div>
			{errors.quantity ? (
				<p id={errorId} role="alert" className="text-sm text-destructive">
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
