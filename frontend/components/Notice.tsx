import type { ReactNode } from "react";

type Kind = "loading" | "error" | "empty";

interface Props {
  kind: Kind;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}

/** One block for the three states every data view needs. Errors interrupt; loading and empty do not. */
export function Notice({ kind, title, children, action }: Props) {
  return (
    <div className={`notice notice--${kind}`} role={kind === "error" ? "alert" : "status"}>
      <p className="notice__title">{title}</p>
      {children ? <p className="notice__body">{children}</p> : null}
      {action ? <div className="notice__action">{action}</div> : null}
    </div>
  );
}
