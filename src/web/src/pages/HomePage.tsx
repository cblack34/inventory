import { HistorySection } from "@/features/history/HistorySection";
import { StockSection } from "@/features/stock/StockSection";

export function HomePage() {
	return (
		<div className="flex flex-col gap-6">
			<h1 className="text-xl font-semibold">Home</h1>
			<StockSection />
			<HistorySection />
		</div>
	);
}
