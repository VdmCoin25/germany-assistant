import { Input as TgInput, Select as TgSelect, Switch as TgSwitch } from "@telegram-apps/telegram-ui";
import type { ComponentProps } from "react";

// TelegramUI draws `header` as a visual caption only. These wrappers give each control the same
// accessible name, so screen readers announce "City" and axe's label rules pass.
export function Input(p: ComponentProps<typeof TgInput>) {
  return <TgInput aria-label={typeof p.header === "string" ? p.header : undefined} {...p} />;
}

export function Select(p: ComponentProps<typeof TgSelect>) {
  return <TgSelect aria-label={typeof p.header === "string" ? p.header : undefined} {...p} />;
}

export function Switch(p: ComponentProps<typeof TgSwitch> & { label: string }) {
  const { label, ...rest } = p;
  return <TgSwitch aria-label={label} {...rest} />;
}
