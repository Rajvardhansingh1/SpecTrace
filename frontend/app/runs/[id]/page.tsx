import type { Metadata } from "next";
import { RunView } from "@/components/RunView";

export const metadata: Metadata = { title: "Comparison" };

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <RunView id={id} />;
}
