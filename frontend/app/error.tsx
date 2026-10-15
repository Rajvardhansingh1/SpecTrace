"use client";

export default function ErrorPage({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="notice notice--error" role="alert">
      <p className="notice__title">This page failed to render</p>
      <p className="notice__body">Reload it. If it fails again, the comparison data may be malformed.</p>
      <div className="notice__action">
        <button type="button" className="button" onClick={reset}>
          Try again
        </button>
      </div>
    </div>
  );
}
