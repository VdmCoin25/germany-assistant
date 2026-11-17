import { List, Section } from "@telegram-apps/telegram-ui";
import { ActionButton } from "../components/ActionButton";
import { RouteCell } from "../components/RouteCell";
import type { T } from "../i18n";

/** J3 review page: one button in its four states and one board cell in its four statuses. */
export function Kit({ t }: { t: T }) {
  return (
    <div className="kit">
      <h3>Button · normal</h3><ActionButton>{t("btn.fillProfile")}</ActionButton>
      <h3>Button · pressed</h3><div className="pressed"><ActionButton>{t("btn.fillProfile")}</ActionButton></div>
      <h3>Button · disabled + reason</h3><ActionButton missing={t("form.pickCity")}>{t("btn.next")}</ActionButton>
      <h3>Button · loading</h3><ActionButton loading>{t("btn.fillProfile")}</ActionButton>
      <h3>Cell · four statuses</h3>
      <List>
        <Section>
          <RouteCell title={t("jobs.title")} explain={t("jobs.new")} status="boarding" statusText={t("status.boarding")} onClick={() => {}} />
          <RouteCell title={t("jobs.title")} explain={t("jobs.review")} status="enroute" statusText={t("status.enroute")} onClick={() => {}} />
          <RouteCell title={t("jobs.title")} explain={t("route.contact")} status="arrived" statusText={t("status.arrived")} onClick={() => {}} />
          <RouteCell title={t("reference.title")} explain={t("soon")} status="expected" statusText={t("status.expected")} />
        </Section>
      </List>
    </div>
  );
}
