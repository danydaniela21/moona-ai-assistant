import { platforms } from "./indicators.mjs";
import { createMonitor } from "./monitor.mjs";
import { createSynchronizer } from "./sync.mjs";

const heartbeat = "moona-connect-heartbeat";
const sync = createSynchronizer(chrome);
const monitor = createMonitor(chrome);

function refresh() {
  void sync();
}

chrome.tabs.onUpdated.addListener((_id, change, tab) => {
  if (change.url || change.status || change.discarded !== undefined || change.frozen !== undefined ||
      (change.title !== undefined && platforms.some(({ origin }) =>
        tab.url?.startsWith(origin.slice(0, -1))
      ))) {
    refresh();
  }
});
// Chrome no siempre incluye el origen anterior al cerrar o reemplazar una pestaña.
// Solo se vuelven a consultar los hosts permitidos y se publica si cambia el estado.
chrome.tabs.onRemoved.addListener(refresh);
chrome.tabs.onReplaced.addListener(refresh);
chrome.permissions.onAdded.addListener(({ origins }) => {
  void monitor.permissionAdded(origins).then(refresh, refresh);
});
chrome.permissions.onRemoved.addListener(refresh);
chrome.runtime.onStartup.addListener(() => {
  refresh();
  // Da a Chrome tiempo para exponer las pestañas restauradas antes de abrir ninguna.
  setTimeout(() => void monitor.start().then(refresh, refresh), 1500);
});
chrome.windows.onCreated.addListener((window) => {
  if (window.type === "normal" && !window.incognito) {
    void monitor.resume().then(refresh, refresh);
  }
});
chrome.runtime.onInstalled.addListener(refresh);
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === heartbeat) void sync(true);
});
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (sender.id !== chrome.runtime.id) return false;
  if (message === "refresh") sync(true).then(respond, () => respond(null));
  else if (message?.type === "setMonitoring" && typeof message.enabled === "boolean") {
    monitor.setEnabled(message.enabled).then(
      (enabled) => { refresh(); respond({ enabled }); },
      () => { refresh(); respond(null); },
    );
  } else return false;
  return true;
});

// Chrome puede descartar alarmas al reiniciar el perfil.
void chrome.alarms.get(heartbeat).then((alarm) => {
  if (!alarm) return chrome.alarms.create(heartbeat, { periodInMinutes: 1 });
}).catch(() => {});
