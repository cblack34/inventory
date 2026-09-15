import type { ComponentProps } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type CountFieldProps = {
	id: string;
	label: string;
	error?: string;
	inputProps: ComponentProps<typeof Input>;
};

/**
 * One labeled numeric input for a visit row (counted, tossed, pulled,
 * added, taken, returned). Shared so every count field in the stand and
 * market forms looks and behaves the same; it carries no validation of its
 * own — the caller's zod schema does that — so it stays a plain view.
 */
export function CountField({ id, label, error, inputProps }: CountFieldProps) {
	const errorId = `${id}-error`;

	return (
		<div className="flex flex-col gap-1">
			<Label htmlFor={id}>{label}</Label>
			<Input
				id={id}
				type="number"
				inputMode="numeric"
				aria-invalid={error ? true : undefined}
				aria-describedby={error ? errorId : undefined}
				{...inputProps}
			/>
			{error ? (
				<p id={errorId} role="alert" className="text-sm text-destructive">
					{error}
				</p>
			) : null}
		</div>
	);
}
