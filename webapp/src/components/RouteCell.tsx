import { Cell } from "@telegram-apps/telegram-ui";
import type { ReactNode } from "react";

export type Status = "boarding" | "enroute" | "arrived" | "expected";

type Props = { title: string; explain: string; status: Status; statusText: string; onClick?: () => void; children?: ReactNode };

/** A departure on the board: a route with its status label and a one-line explanation,
 *  so the metaphor never carries the meaning alone. */
export function RouteCell({ title, explain, status, statusText, onClick }: Props) {
  return (
    <Cell onClick={onClick} subtitle={explain} multiline aria-disabled={status === "expected" || undefined}
          after={<span className={`status status--${status}`}>{statusText}</span>}>
      {title}
    </Cell>
  );
}
