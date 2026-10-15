"use client";

import { useMemo, useState } from "react";
import { CLASSIFICATION_LABEL, CLASSIFICATION_ORDER, sortChanges } from "@/lib/format";
import type { Change, Classification, Impact } from "@/lib/types";
import { ChangeTypeText, ClassificationTag } from "./Tags";

interface Props {
  changes: Change[];
  impacts: Record<string, Impact[]>;
  selectedKey: string | null;
  onSelect: (key: string) => void;
}

export function ChangeList({ changes, impacts, selectedKey, onSelect }: Props) {
  const [filter, setFilter] = useState<Classification | "all">("all");
  const sorted = useMemo(() => sortChanges(changes), [changes]);
  const counts = useMemo(() => {
    const out = new Map<Classification, number>();
    for (const c of changes) out.set(c.classification, (out.get(c.classification) ?? 0) + 1);
    return out;
  }, [changes]);
  const visible = filter === "all" ? sorted : sorted.filter((c) => c.classification === filter);

  return (
    <div>
      <div className="filters" role="group" aria-label="Filter changes by classification">
        <button
          type="button"
          className="filter"
          aria-pressed={filter === "all"}
          onClick={() => setFilter("all")}
        >
          All ({changes.length})
        </button>
        {CLASSIFICATION_ORDER.filter((c) => counts.has(c)).map((c) => (
          <button
            key={c}
            type="button"
            className="filter"
            aria-pressed={filter === c}
            onClick={() => setFilter(c)}
          >
            {CLASSIFICATION_LABEL[c]} ({counts.get(c)})
          </button>
        ))}
      </div>

      <ul className="changes" aria-label="Changes">
        {visible.map((change) => {
          const count = impacts[change.key]?.length ?? 0;
          return (
            <li key={change.key}>
              <button
                type="button"
                className="change"
                aria-current={change.key === selectedKey ? "true" : undefined}
                onClick={() => onSelect(change.key)}
              >
                <span className="change__key mono">{change.key}</span>
                <span className="change__meta">
                  <ClassificationTag value={change.classification} />
                  <ChangeTypeText value={change.change_type} />
                  {change.change_type !== "added" ? (
                    <span className="muted">
                      {count} {count === 1 ? "impact" : "impacts"}
                    </span>
                  ) : null}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
