import { describe, expect, it } from "vitest";
import { parseRouteId } from "./routeId";

describe("parseRouteId", () => {
	it("accepts a plain positive integer string", () => {
		expect(parseRouteId("42")).toBe(42);
	});

	it("rejects undefined", () => {
		expect(parseRouteId(undefined)).toBeNull();
	});

	it("rejects an empty string", () => {
		expect(parseRouteId("")).toBeNull();
	});

	it("rejects negative numbers", () => {
		expect(parseRouteId("-1")).toBeNull();
	});

	it("rejects zero", () => {
		expect(parseRouteId("0")).toBeNull();
	});

	it("rejects exponential notation", () => {
		expect(parseRouteId("1e3")).toBeNull();
	});

	it("rejects decimals", () => {
		expect(parseRouteId("1.5")).toBeNull();
	});

	it("rejects a numeric prefix followed by non-digit characters", () => {
		expect(parseRouteId("1abc")).toBeNull();
	});

	it("rejects unsafe integers that would be rounded before use", () => {
		expect(parseRouteId("9007199254740993")).toBeNull();
	});
});
