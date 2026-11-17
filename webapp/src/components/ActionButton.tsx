import { Button } from "@telegram-apps/telegram-ui";
import { useId, type ReactNode } from "react";

type Props = {
  children: ReactNode;
  onClick?: () => void;
  loading?: boolean;
  /** When set, the button is disabled and this line says what is missing. */
  missing?: string;
  mode?: "filled" | "bezeled" | "plain";
};

/** In-content button. The main action of a screen is Telegram's BottomButton (tg.ts);
 *  this one is for secondary actions inside the content. States: normal, pressed (:active, 100 ms),
 *  disabled with a reason, loading. */
export function ActionButton({ children, onClick, loading = false, missing, mode = "filled" }: Props) {
  const hintId = useId();
  return (
    <div className="action">
      <Button size="l" stretched mode={mode} loading={loading} disabled={!!missing}
              onClick={onClick} aria-describedby={missing ? hintId : undefined} aria-busy={loading || undefined}>
        {children}
      </Button>
      {missing && <p className="action__missing" id={hintId}>{missing}</p>}
    </div>
  );
}
