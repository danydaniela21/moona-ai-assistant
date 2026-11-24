import { platforms } from "./indicators.mjs";
import { MONITORING_KEY } from "./monitor.mjs";

const list = document.querySelector("#platforms");
const template = document.querySelector("#platform-row");
const refresh = document.querySelector("#refresh");
const connection = document.querySelector("#connection");
const monitoring = document.querySelector("#monitoring");
const monitoringError = document.querySelector("#monitoring-error");
const message = (key, value) => chrome.i18n.getMessage(key, value);
document.documentElement.lang = chrome.i18n.getUILanguage().startsWith("en") ? "en" : "es";
refresh.textContent = message("refresh");
list.setAttribute("aria-label", message("platformList"));
document.querySelector("#monitoring-label").textContent = message("automaticMonitoring");
document.querySelector("#monitoring-help").textContent = message("automaticMonitoringHelp");
monitoringError.textContent = message("automaticMonitoringError");

async function readMonitoringPreference() {
  const saved = await chrome.storage.local.get(MONITORING_KEY);
  monitoring.checked = saved[MONITORING_KEY] === true;
}

monitoring.addEventListener("change", async () => {
  monitoring.disabled = true;
  monitoringError.hidden = true;
  try {
    const result = await chrome.runtime.sendMessage({
      type: "setMonitoring", enabled: monitoring.checked,
    });
    if (!result) throw new Error("No response from service worker");
    monitoring.checked = result.enabled;
    await updateAll();
  } catch {
    monitoringError.hidden = false;
    await readMonitoringPreference().catch(() => {});
  } finally {
    monitoring.disabled = false;
  }
});

void readMonitoringPreference().then(
  () => { monitoring.disabled = false; },
  () => { monitoringError.hidden = false; },
);

const rows = new Map(platforms.map((platform) => {
  const row = template.content.firstElementChild.cloneNode(true);
  const status = row.querySelector("p");
  const authorize = row.querySelector("button");
  row.querySelector("strong").textContent = platform.name;
  authorize.textContent = message("authorize");
  authorize.setAttribute("aria-label", message("authorizePlatform", platform.name));

  authorize.addEventListener("click", async () => {
    authorize.disabled = true;
    try {
      await chrome.permissions.request({ origins: [platform.origin] });
      await updateAll();
    } catch {
      status.textContent = message("permissionError");
    } finally {
      authorize.disabled = false;
    }
  });

  list.append(row);
  return [platform.id, { status, authorize }];
}));

async function updateAll() {
  refresh.disabled = true;
  try {
    const result = await chrome.runtime.sendMessage("refresh");
    if (!result) throw new Error("No response from service worker");
    connection.textContent = message(result.connected ? "connected" : "disconnected");
    for (const indicator of result.indicators) {
      const { status, authorize } = rows.get(indicator.platform);
      const { state, value } = indicator;
      status.textContent = value === null
        ? message(state)
        : message("inTitle", `${value}${state === "lower_bound" ? "+" : ""}`);
      authorize.hidden = state !== "unauthorized";
    }
  } catch {
    connection.textContent = message("refreshError");
  } finally {
    refresh.disabled = false;
  }
}

refresh.addEventListener("click", updateAll);
void updateAll();
