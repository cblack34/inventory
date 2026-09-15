import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { request } from "@/api/client";
import type { components } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { problemMessage } from "@/lib/problemMessage";

type LocationRead = components["schemas"]["LocationRead"];
type LocationCreate = components["schemas"]["LocationCreate"];
type LocationPatch = components["schemas"]["LocationPatch"];

// Built-ins created by migration (`docs/data-model.md`, "Concepts"); never
// editable here, matching the API rejecting a rename or deactivation of one.
const BUILT_IN_KINDS = new Set([
	"kitchen",
	"production",
	"sold",
	"waste",
	"sampled",
]);

const createLocationSchema = z.object({
	name: z.string().min(1, "Required"),
	kind: z.enum(["stand", "market"], { message: "Choose a kind" }),
});

type CreateLocationValues = z.infer<typeof createLocationSchema>;

const editLocationSchema = z.object({
	name: z.string().min(1, "Required"),
	active: z.boolean(),
});

type EditLocationValues = z.infer<typeof editLocationSchema>;

/** Locations: list, create a stand or market, rename, and deactivate/reactivate. */
export function LocationsPage() {
	const locationsQuery = useQuery({
		queryKey: ["locations"],
		queryFn: () => request<LocationRead[]>("GET", "/api/v1/locations"),
	});

	return (
		<div className="flex flex-col gap-6">
			<h1 className="text-xl font-semibold">Locations</h1>
			<CreateLocationForm />
			{locationsQuery.isPending ? <p>Loading locations…</p> : null}
			{locationsQuery.isError ? (
				<p role="alert">{problemMessage(locationsQuery.error)}</p>
			) : null}
			{locationsQuery.data ? (
				<section className="flex flex-col gap-3">
					{locationsQuery.data.map((location) => (
						<LocationRow key={location.id} location={location} />
					))}
				</section>
			) : null}
		</div>
	);
}

function CreateLocationForm() {
	const queryClient = useQueryClient();
	const {
		register,
		handleSubmit,
		control,
		reset,
		formState: { errors },
	} = useForm<CreateLocationValues>({
		resolver: zodResolver(createLocationSchema),
		defaultValues: { name: "", kind: "stand" },
	});

	const create = useMutation({
		mutationFn: (values: CreateLocationValues) => {
			const body: LocationCreate = { name: values.name, kind: values.kind };
			return request<LocationRead>("POST", "/api/v1/locations", body);
		},
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: ["locations"] });
			reset({ name: "", kind: "stand" });
		},
	});

	const onSubmit = handleSubmit((values) => create.mutate(values));

	return (
		<Card>
			<CardHeader>
				<CardTitle asChild>
					<h2>Add stand or market</h2>
				</CardTitle>
			</CardHeader>
			<CardContent>
				<form onSubmit={onSubmit} className="flex flex-col gap-3">
					<div className="flex flex-col gap-1.5">
						<Label htmlFor="new-location-name">Name</Label>
						<Input
							id="new-location-name"
							aria-invalid={errors.name ? true : undefined}
							{...register("name")}
						/>
						{errors.name ? (
							<p role="alert" className="text-sm text-destructive">
								{errors.name.message}
							</p>
						) : null}
					</div>
					<div className="flex flex-col gap-1.5">
						<Label htmlFor="new-location-kind">Kind</Label>
						<Controller
							control={control}
							name="kind"
							render={({ field }) => (
								<Select value={field.value} onValueChange={field.onChange}>
									<SelectTrigger id="new-location-kind" className="w-full">
										<SelectValue />
									</SelectTrigger>
									<SelectContent>
										<SelectItem value="stand">Stand</SelectItem>
										<SelectItem value="market">Market</SelectItem>
									</SelectContent>
								</Select>
							)}
						/>
						{errors.kind ? (
							<p role="alert" className="text-sm text-destructive">
								{errors.kind.message}
							</p>
						) : null}
					</div>
					{create.isError ? (
						<p role="alert" className="text-sm text-destructive">
							{problemMessage(create.error)}
						</p>
					) : null}
					<Button
						type="submit"
						disabled={create.isPending}
						className="self-start"
					>
						{create.isPending ? "Adding…" : "Add location"}
					</Button>
				</form>
			</CardContent>
		</Card>
	);
}

function LocationRow({ location }: { location: LocationRead }) {
	const [editing, setEditing] = useState(false);
	const isBuiltIn = BUILT_IN_KINDS.has(location.kind);

	if (editing && !isBuiltIn) {
		return (
			<EditLocationForm location={location} onDone={() => setEditing(false)} />
		);
	}

	return (
		<Card>
			<CardHeader>
				<CardTitle className="flex items-center justify-between gap-2">
					<span className="min-w-0 break-words">{location.name}</span>
					<span className="flex items-center gap-1.5">
						{isBuiltIn ? <Badge variant="secondary">Built-in</Badge> : null}
						{!location.active ? (
							<Badge variant="outline">Inactive</Badge>
						) : null}
					</span>
				</CardTitle>
			</CardHeader>
			<CardContent className="flex flex-col gap-2">
				<p className="text-sm text-muted-foreground capitalize">
					{location.kind}
				</p>
				{isBuiltIn ? null : (
					<Button
						type="button"
						size="sm"
						variant="outline"
						className="self-start"
						aria-label={`Edit ${location.name}`}
						onClick={() => setEditing(true)}
					>
						Edit
					</Button>
				)}
			</CardContent>
		</Card>
	);
}

function EditLocationForm({
	location,
	onDone,
}: {
	location: LocationRead;
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const {
		register,
		handleSubmit,
		control,
		formState: { errors },
	} = useForm<EditLocationValues>({
		resolver: zodResolver(editLocationSchema),
		defaultValues: { name: location.name, active: location.active },
	});

	const update = useMutation({
		mutationFn: (values: EditLocationValues) => {
			const body: LocationPatch = { name: values.name, active: values.active };
			return request<LocationRead>(
				"PATCH",
				`/api/v1/locations/${location.id}`,
				body,
			);
		},
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: ["locations"] });
			onDone();
		},
	});

	const onSubmit = handleSubmit((values) => update.mutate(values));

	return (
		<Card>
			<CardHeader>
				<CardTitle asChild>
					<h2 className="min-w-0 break-words">Edit {location.name}</h2>
				</CardTitle>
			</CardHeader>
			<CardContent>
				<form onSubmit={onSubmit} className="flex flex-col gap-3">
					<div className="flex flex-col gap-1.5">
						<Label htmlFor={`edit-location-name-${location.id}`}>Name</Label>
						<Input
							id={`edit-location-name-${location.id}`}
							aria-invalid={errors.name ? true : undefined}
							{...register("name")}
						/>
						{errors.name ? (
							<p role="alert" className="text-sm text-destructive">
								{errors.name.message}
							</p>
						) : null}
					</div>
					<div className="flex items-center gap-2">
						<Controller
							control={control}
							name="active"
							render={({ field }) => (
								<Switch
									id={`edit-location-active-${location.id}`}
									checked={field.value}
									onCheckedChange={field.onChange}
								/>
							)}
						/>
						<Label htmlFor={`edit-location-active-${location.id}`}>
							Active
						</Label>
					</div>
					{update.isError ? (
						<p role="alert" className="text-sm text-destructive">
							{problemMessage(update.error)}
						</p>
					) : null}
					<div className="flex gap-2">
						<Button type="submit" size="sm" disabled={update.isPending}>
							{update.isPending ? "Saving…" : "Save"}
						</Button>
						<Button
							type="button"
							size="sm"
							variant="ghost"
							onClick={onDone}
							disabled={update.isPending}
						>
							Cancel
						</Button>
					</div>
				</form>
			</CardContent>
		</Card>
	);
}
