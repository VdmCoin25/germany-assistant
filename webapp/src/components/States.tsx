import { Placeholder } from "@telegram-apps/telegram-ui";
import type { T } from "../i18n";
import { tg, useBottomButton } from "../tg";

/** Loading: the shape of the board and the first rows, no spinner. */
export function HomeSkeleton({ t }: { t: T }) {
  return (
    <div aria-busy="true">
      <p className="sr">{t("loading")}</p>
      <div className="board board--full skel-board"><span className="skel skel--light" style={{ width: "40%" }} />
        <span className="skel skel--light skel--big" style={{ width: "55%" }} /></div>
      <div className="skel-rows">
        <span className="skel" style={{ width: "30%" }} /><span className="skel" style={{ width: "75%" }} />
        <span className="skel skel--route" />
      </div>
    </div>
  );
}

const closeApp = () => tg?.close?.();

/** Error in plain words; the one main action depends on what can actually help.
 *  401: the signed session expired, retrying cannot help — reopen from the bot.
 *  403: the account is blocked. Anything else: network or server, retry. */
export function LoadError({ t, status, retry }: { t: T; status: number; retry: () => void }) {
  const kind = status === 401 ? "expired" : status === 403 ? "blocked" : "retry";
  useBottomButton(kind === "retry" ? t("btn.retry") : kind === "expired" ? t("btn.close") : null,
                  kind === "retry" ? retry : closeApp);
  if (kind === "expired") return <Placeholder header={t("load.expired")} description={t("load.expiredHint")} />;
  if (kind === "blocked") return <Placeholder header={t("load.blocked")} description={t("load.blockedHint")} />;
  return <Placeholder header={t("load.error")} description={t("load.errorHint")} />;
}

export function OfflineNote({ t }: { t: T }) {
  return <p className="offline" role="status">{t("offline")}</p>;
}

/** Opened outside Telegram (no signed initData): explain and point to the bot. */
export function OutsideTelegram({ t, bot }: { t: T; bot: string }) {
  return (
    <Placeholder header={t("outside.title")} description={t("outside.text")}
      action={<a className="link-button" href={`https://t.me/${bot}`}>{t("btn.openBot")}</a>} />
  );
}
