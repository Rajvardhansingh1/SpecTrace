import { CHANGE_TYPE_LABEL, CLASSIFICATION_LABEL, percent } from "@/lib/format";
import type { ChangeType, Classification, Label } from "@/lib/types";

/** Each class has its own shape and its own word, so color is never the only signal. */
export function ClassificationTag({ value }: { value: Classification }) {
  return (
    <span className={`tag tag--${value}`}>
      <span className="tag__mark" aria-hidden="true" />
      {CLASSIFICATION_LABEL[value]}
    </span>
  );
}

/** Confirmed has a solid outline, inferred a dashed one. The word is always present. */
export function CertaintyTag({ value, confidence }: { value: Label; confidence?: number }) {
  return (
    <span className={`certainty certainty--${value}`}>
      {value === "confirmed" ? "Confirmed" : "Inferred"}
      {confidence !== undefined && value === "inferred" ? ` ${percent(confidence)}` : ""}
    </span>
  );
}

export function ChangeTypeText({ value }: { value: ChangeType }) {
  return <span className="muted">{CHANGE_TYPE_LABEL[value]}</span>;
}
