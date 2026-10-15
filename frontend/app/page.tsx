import type { Metadata } from "next";
import { CompareForm } from "@/components/CompareForm";

export const metadata: Metadata = { title: "Compare two versions" };

export default function Page() {
  return (
    <>
      <h1>Compare two versions</h1>
      <p className="lede">
        Add the OpenAPI files and Markdown docs for each version. SpecTrace lists what changed, then shows
        which docs, requirements and examples depend on each change and the source line that proves it.
      </p>
      <CompareForm />
    </>
  );
}
