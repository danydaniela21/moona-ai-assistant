const badge = String.raw`\(([0-9]{1,9})(\+)?\)`;

export const platforms = [
  {
    id: "instagram", name: "Instagram", origin: "https://www.instagram.com/*",
    label: "Instagram",
  },
  {
    id: "facebook", name: "Facebook", origin: "https://www.facebook.com/*",
    label: "Facebook",
  },
  {
    id: "whatsapp", name: "WhatsApp Web", origin: "https://web.whatsapp.com/*",
    label: "WhatsApp(?: Web)?",
  },
  {
    id: "linkedin", name: "LinkedIn", origin: "https://www.linkedin.com/*",
    label: "(?:(?:Feed|Inicio)\\s*\\|\\s*)?LinkedIn",
  },
];

export function parseIndicator(platform, title) {
  if (typeof title !== "string") return null;
  const { label } = platform;
  const text = title.trim();
  const match = text.match(new RegExp(`^${badge}\\s+${label}$`, "iu"))
    ?? text.match(new RegExp(`^${label}\\s+${badge}$`, "iu"));
  if (!match) return null;
  const value = Number(match[1]);
  const lowerBound = Boolean(match[2]);
  if (lowerBound && value === 0) return null;
  return { value, lowerBound };
}

export async function readPlatform(platform, browser) {
  const origins = [platform.origin];
  if (!(await browser.permissions.contains({ origins }))) {
    return { state: "unauthorized" };
  }

  const tabs = await browser.tabs.query({ url: origins });
  // Un permiso revocado durante la consulta puede producir una lista vacía.
  if (!(await browser.permissions.contains({ origins }))) {
    return { state: "unauthorized" };
  }
  if (tabs.length === 0) return { state: "no_tab" };

  const indicators = tabs.map((tab) =>
    tab.discarded || tab.frozen || tab.status === "loading" ? null : parseIndicator(platform, tab.title)
  );
  const first = indicators[0];
  if (!first || !indicators.every((item) =>
    item?.value === first.value && item.lowerBound === first.lowerBound
  )) {
    return { state: "unknown" };
  }
  return { state: "observed", ...first };
}
