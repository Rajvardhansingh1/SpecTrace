"use client";

import { useId, useRef } from "react";
import { ACCEPT, byteLength, formatBytes, readFiles, totalBytes } from "@/lib/files";
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

export function VersionPane({ side, heading, label, files, onLabel, onAdd, onRemove }: Props) {
  const inputId = useId();
  const filePicker = useRef<HTMLInputElement>(null);
  const folderPicker = useRef<HTMLInputElement>(null);
  const names = Object.keys(files).sort();

  async function pick(list: FileList | null, fromFolder: boolean) {
    if (!list || list.length === 0) return;
    const { files: added, skipped } = await readFiles(Array.from(list), fromFolder);
    onAdd(added, skipped);
  }

  return (
    <fieldset className="pane">
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
            void pick(e.target.files, false);
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
            void pick(e.target.files, true);
            e.target.value = "";
          }}
        />
      </div>

      {names.length === 0 ? (
        <p className="muted pane__empty">
          No files yet. Add OpenAPI YAML or JSON and the Markdown docs for this version.
        </p>
      ) : (
        <>
          <p className="muted" aria-live="polite">
            {names.length} {names.length === 1 ? "file" : "files"}, {formatBytes(totalBytes(files))}
          </p>
          <ul className="filelist">
            {names.map((name) => (
              <li key={name}>
                <span className="mono filelist__name">{name}</span>
                <span className="muted filelist__size">{formatBytes(byteLength(files[name]))}</span>
                <button
                  type="button"
                  className="button button--quiet"
                  onClick={() => onRemove(name)}
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
