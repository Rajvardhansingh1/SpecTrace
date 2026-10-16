"use client";

import { useId, useRef, useState } from "react";
import { ACCEPT, byteLength, collectDropped, formatBytes, readFiles, totalBytes } from "@/lib/files";
import type { VersionFiles } from "@/lib/types";

interface Props {
  side: "A" | "B";
  heading: string;
  label: string;
  files: VersionFiles;
  onLabel: (label: string) => void;
  onAdd: (added: VersionFiles, skipped: string[]) => void;
  onRemove: (name: string) => void;
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

export function VersionPane({ side, heading, label, files, onLabel, onAdd, onRemove }: Props) {
  const inputId = useId();
  const filePicker = useRef<HTMLInputElement>(null);
  const folderPicker = useRef<HTMLInputElement>(null);
  const names = Object.keys(files).sort();

  // Drag events fire for every child element, so entering and leaving are counted.
  const dragDepth = useRef(0);
  const [dragging, setDragging] = useState(false);
  // A persistent polite region: what was added is spoken as well as shown.
  const [status, setStatus] = useState("");

  async function ingest(list: File[], fromFolder: boolean, notes: string[] = []) {
    if (list.length === 0 && notes.length === 0) return;
    const { files: added, skipped } = await readFiles(list, fromFolder);
    const allSkipped = [...skipped, ...notes];
    const count = Object.keys(added).length;
    setStatus(
      `${count === 0 ? "No files added" : `Added ${plural(count, "file")}`}` +
        (allSkipped.length > 0 ? `, ${allSkipped.length} skipped.` : "."),
    );
    onAdd(added, allSkipped);
  }

  const carriesFiles = (e: React.DragEvent) => Array.from(e.dataTransfer.types).includes("Files");

  function onDrop(e: React.DragEvent) {
    if (!carriesFiles(e)) return;
    e.preventDefault();
    dragDepth.current = 0;
    setDragging(false);
    // collectDropped reads the entries before its first await, which is what the browser requires.
    void collectDropped(e.dataTransfer).then((d) => ingest(d.files, d.fromFolder, d.notes));
  }

  return (
    <fieldset
      className={dragging ? "pane pane--drag" : "pane"}
      onDragEnter={(e) => {
        if (!carriesFiles(e)) return;
        e.preventDefault();
        dragDepth.current += 1;
        setDragging(true);
      }}
      onDragOver={(e) => {
        if (!carriesFiles(e)) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "copy";
      }}
      onDragLeave={(e) => {
        if (!carriesFiles(e)) return;
        dragDepth.current = Math.max(0, dragDepth.current - 1);
        if (dragDepth.current === 0) setDragging(false);
      }}
      onDrop={onDrop}
    >
      <legend className="pane__legend">{heading}</legend>

      <div className="field">
        <label htmlFor={inputId}>Name of this version</label>
        <input
          id={inputId}
          type="text"
          value={label}
          maxLength={100}
          onChange={(e) => onLabel(e.target.value)}
          autoComplete="off"
        />
      </div>

      <div className="pane__buttons">
        <button type="button" className="button" onClick={() => filePicker.current?.click()}>
          Add files
        </button>
        <button type="button" className="button" onClick={() => folderPicker.current?.click()}>
          Add folder
        </button>
        <input
          ref={filePicker}
          type="file"
          multiple
          accept={ACCEPT}
          hidden
          aria-label={`Choose files for version ${side}`}
          data-testid={`files-${side}`}
          onChange={(e) => {
            void ingest(Array.from(e.target.files ?? []), false);
            e.target.value = "";
          }}
        />
        <input
          ref={folderPicker}
          type="file"
          hidden
          aria-label={`Choose a folder for version ${side}`}
          data-testid={`folder-${side}`}
          // webkitdirectory is not in React's typings but is supported by every current browser.
          {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
          onChange={(e) => {
            void ingest(Array.from(e.target.files ?? []), true);
            e.target.value = "";
          }}
        />
      </div>

      <p className={dragging ? "pane__drop pane__drop--active" : "pane__drop muted"}>
        {dragging
          ? `Release to add these to version ${side}.`
          : "You can also drag files or a folder onto this box."}
      </p>

      <p className="muted" aria-live="polite" data-testid={`status-${side}`}>
        {status}
      </p>

      {names.length === 0 ? (
        <p className="muted pane__empty">
          No files yet. Add OpenAPI YAML or JSON and the Markdown docs for this version.
        </p>
      ) : (
        <>
          <p className="muted">
            {plural(names.length, "file")}, {formatBytes(totalBytes(files))}
          </p>
          <ul className="filelist">
            {names.map((name) => (
              <li key={name}>
                <span className="mono filelist__name">{name}</span>
                <span className="muted filelist__size">{formatBytes(byteLength(files[name]))}</span>
                <button
                  type="button"
                  className="button button--quiet"
                  onClick={() => {
                    onRemove(name);
                    setStatus(`Removed ${name}.`);
                  }}
                  aria-label={`Remove ${name} from version ${side}`}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </fieldset>
  );
}
