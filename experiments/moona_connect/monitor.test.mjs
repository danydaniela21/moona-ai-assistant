import assert from "node:assert/strict";
import { test } from "node:test";
import { platforms, readPlatform } from "./indicators.mjs";
import { createMonitor, MONITORING_KEY } from "./monitor.mjs";

const [instagram, facebook, whatsapp, linkedin] = platforms;
const home = (platform) => platform.origin.slice(0, -1);

function harness() {
  function storage() {
    const values = new Map();
    return {
      get: async (key) => ({ [key]: values.get(key) }),
      set: async (entries) => {
        for (const [key, value] of Object.entries(entries)) values.set(key, value);
      },
      remove: async (key) => values.delete(key),
    };
  }

  const windows = [{ id: 2 }, { id: 5, focused: true }, { id: 8, incognito: true }];
  const tabs = [];
  const created = [];
  const grants = new Set();
  const browser = {
    storage: { local: storage(), session: storage() },
    permissions: { contains: async ({ origins }) => grants.has(origins[0]) },
    windows: {
      getAll: async (query) => {
        assert.deepEqual(query, { windowTypes: ["normal"] });
        return windows;
      },
    },
    tabs: {
      query: async (filter) => filter.status
        ? tabs.filter((tab) => tab.status === filter.status)
        : tabs.filter((tab) => tab.url?.startsWith(filter.url[0].slice(0, -1))),
      create: async (options) => {
        created.push(options);
        tabs.push({ url: options.url, windowId: options.windowId, active: options.active });
      },
    },
  };
  return { browser, windows, tabs, created, grants };
}

test("no abre pestañas antes del consentimiento, incluso al iniciar o conceder un sitio", async () => {
  const { browser, created, grants } = harness();
  grants.add(instagram.origin);
  const monitor = createMonitor(browser);
  await monitor.start();
  await monitor.permissionAdded([instagram.origin]);
  await monitor.resume();
  assert.deepEqual(created, []);
  assert.notEqual((await browser.storage.local.get(MONITORING_KEY))[MONITORING_KEY], true);
});

test("abre únicamente sitios autorizados, en segundo plano y sin duplicados entre ventanas", async () => {
  const { browser, tabs, created, grants } = harness();
  [instagram, facebook, whatsapp].forEach((platform) => grants.add(platform.origin));
  tabs.push({ url: home(facebook) + "feed", windowId: 2, discarded: true });
  tabs.push({ url: "about:blank", pendingUrl: home(whatsapp), status: "loading" });
  tabs.push({ url: home(instagram), incognito: true });
  const monitor = createMonitor(browser);
  await Promise.all([monitor.setEnabled(true), monitor.start(), monitor.resume()]);
  assert.deepEqual(created, [{ url: home(instagram), windowId: 5, active: false }]);
  assert.equal((await browser.storage.local.get(MONITORING_KEY))[MONITORING_KEY], true);
});

test("recuerda el consentimiento y espera una ventana normal sin crear una nueva", async () => {
  const { browser, windows, created, grants } = harness();
  grants.add(whatsapp.origin);
  windows.splice(0, windows.length, { id: 8, incognito: true });
  await createMonitor(browser).setEnabled(true);
  assert.deepEqual(created, []);
  windows.push({ id: 12 });
  await createMonitor(browser).resume();
  assert.deepEqual(created, [{ url: home(whatsapp), windowId: 12, active: false }]);
});

test("abre un permiso nuevo, respeta un cierre y desactiva futuras aperturas", async () => {
  const { browser, tabs, created, grants } = harness();
  grants.add(instagram.origin);
  const monitor = createMonitor(browser);
  await monitor.setEnabled(true);
  tabs.pop();
  grants.add(linkedin.origin);
  await monitor.permissionAdded([linkedin.origin, "https://example.org/*"]);
  await monitor.resume();
  assert.deepEqual(created.map((tab) => tab.url), [home(instagram), home(linkedin)]);
  await monitor.setEnabled(false);
  const openTabs = [...tabs];
  await createMonitor(browser).start();
  assert.deepEqual(tabs, openTabs);
  assert.equal(created.length, 2);
});

test("una revocación durante la búsqueda evita que se abra la pestaña", async () => {
  const { browser, created, grants } = harness();
  grants.add(instagram.origin);
  const query = browser.tabs.query;
  browser.tabs.query = (filter) => {
    grants.delete(instagram.origin);
    return query(filter);
  };
  await createMonitor(browser).setEnabled(true);
  assert.deepEqual(created, []);
});

test("desactivar el monitoreo cancela las aperturas que todavía están en preparación", async () => {
  const { browser, created, grants } = harness();
  grants.add(instagram.origin);
  const query = browser.tabs.query;
  const monitor = createMonitor(browser);
  let stopping;
  browser.tabs.query = (filter) => {
    stopping ??= monitor.setEnabled(false);
    return query(filter);
  };
  await monitor.setEnabled(true);
  await stopping;
  assert.deepEqual(created, []);
  assert.equal((await browser.storage.local.get(MONITORING_KEY))[MONITORING_KEY], false);
});

test("una pestaña congelada o descartada aporta un indicador desconocido", async () => {
  const { browser, tabs, grants } = harness();
  grants.add(instagram.origin);
  for (const suspended of [{ frozen: true }, { discarded: true }]) {
    tabs.splice(0, tabs.length, { url: home(instagram), title: "(3) Instagram", ...suspended });
    assert.deepEqual(await readPlatform(instagram, browser), { state: "unknown" });
  }
});
