import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { parseIndicator, platforms, readPlatform } from "./indicators.mjs";
import { createSynchronizer } from "./sync.mjs";

const [instagram, facebook, whatsapp, linkedin] = platforms;
const observed = (value, lowerBound = false) => ({ value, lowerBound });

test("el manifiesto solo declara los cuatro orígenes opcionales", () => {
  const manifest = JSON.parse(readFileSync(new URL("./manifest.json", import.meta.url)));
  assert.equal(manifest.manifest_version, 3);
  assert.deepEqual(manifest.optional_host_permissions, platforms.map(({ origin }) => origin));
  assert.deepEqual(manifest.permissions, ["alarms", "nativeMessaging", "storage"]);
  assert.equal(manifest.background.service_worker, "background.mjs");
  for (const key of ["host_permissions", "content_scripts", "externally_connectable"]) {
    assert.equal(manifest[key], undefined);
  }
  assert.match(manifest.content_security_policy.extension_pages, /connect-src 'none'/);
});

test("publica únicamente los cuatro campos autorizados y renueva el estado a demanda", async () => {
  const sent = [];
  let tabs = [{ title: "(7+) Instagram", url: "https://www.instagram.com/privado" }];
  const browser = {
    permissions: { contains: async ({ origins }) => origins[0] === instagram.origin },
    tabs: { query: async () => tabs },
    runtime: {
      sendNativeMessage: async (host, data) => {
        assert.equal(host, "com.moona.connect");
        sent.push(data);
        return { ok: true };
      },
    },
  };
  let now = new Date("2026-11-24T16:00:00.000Z");
  const sync = createSynchronizer(browser, () => now);
  assert.equal((await sync()).connected, true);
  assert.deepEqual(sent[0].indicators[0], {
    platform: "instagram", state: "lower_bound", value: 7, updated_at: now.toISOString(),
  });
  assert.deepEqual(sent[0].indicators.map((item) => item.state),
    ["lower_bound", "unauthorized", "unauthorized", "unauthorized"]);
  assert.ok(!JSON.stringify(sent).includes("privado"));
  await sync();
  assert.equal(sent.length, 1);

  tabs = [];
  await sync();
  assert.equal(sent[1].indicators[0].state, "no_tab");
  assert.equal(sent[1].indicators[0].value, null);
  now = new Date("2026-11-24T16:01:00.000Z");
  await sync(true);
  assert.equal(sent[2].indicators[0].updated_at, now.toISOString());
});

test("conserva la lectura local y vuelve a intentar cuando el host falla", async () => {
  let attempts = 0;
  const browser = {
    permissions: { contains: async () => true },
    tabs: { query: async () => [{ title: "(3) Instagram" }] },
    runtime: {
      sendNativeMessage: async () => {
        if (++attempts === 1) throw new Error("Host not registered");
        return { ok: true };
      },
    },
  };
  const sync = createSynchronizer(browser);
  const first = await sync();
  assert.equal(first.connected, false);
  assert.equal(first.indicators[0].value, 3);
  assert.equal((await sync()).connected, true);
  assert.equal(attempts, 2);
});

test("el worker se activa por título autorizado, cierre, alarma y botón manual", async () => {
  const listeners = new Map();
  const event = (name) => ({ addListener: (callback) => listeners.set(name, callback) });
  const sent = [];
  let tabs = [{ title: "(3) Instagram" }];
  const fakeChrome = {
    tabs: {
      query: async () => tabs,
      onUpdated: event("updated"),
      onRemoved: event("removed"),
      onReplaced: event("replaced"),
    },
    permissions: {
      contains: async ({ origins }) => origins[0] === instagram.origin,
      onAdded: event("added"),
      onRemoved: event("revoked"),
    },
    windows: { onCreated: event("window-created") },
    alarms: {
      get: async () => null,
      create: async (name, settings) => {
        assert.equal(name, "moona-connect-heartbeat");
        assert.equal(settings.periodInMinutes, 1);
      },
      onAlarm: event("alarm"),
    },
    runtime: {
      id: "local-extension",
      onStartup: event("startup"),
      onInstalled: event("installed"),
      onMessage: event("message"),
      sendNativeMessage: async (_host, data) => {
        sent.push(data);
        return { ok: true };
      },
    },
  };
  globalThis.chrome = fakeChrome;
  try {
    await import("./background.mjs");
    const drain = () => new Promise((resolve) => setImmediate(resolve));
    listeners.get("updated")(1, { title: "(3) Instagram" }, { url: "https://example.org/" });
    await drain();
    assert.equal(sent.length, 0);
    listeners.get("updated")(2, { title: "(3) Instagram" }, { url: "https://www.instagram.com/" });
    await drain();
    assert.equal(sent[0].indicators[0].value, 3);
    tabs = [];
    listeners.get("removed")(2);
    await drain();
    assert.equal(sent[1].indicators[0].state, "no_tab");
    listeners.get("alarm")({ name: "moona-connect-heartbeat" });
    await drain();
    assert.equal(sent.length, 3);
    const reply = await new Promise((resolve) => {
      const keepOpen = listeners.get("message")("refresh", { id: fakeChrome.runtime.id }, resolve);
      assert.equal(keepOpen, true);
    });
    assert.equal(reply.connected, true);
    assert.equal(sent.length, 4);
  } finally {
    delete globalThis.chrome;
  }
});

test("acepta indicadores aislados, cero explícito y límites inferiores", () => {
  assert.deepEqual(parseIndicator(instagram, "(2) Instagram"), observed(2));
  assert.deepEqual(parseIndicator(facebook, "Facebook (0)"), observed(0));
  assert.deepEqual(parseIndicator(whatsapp, "(99+) WhatsApp Web"), observed(99, true));
  assert.deepEqual(parseIndicator(linkedin, "(4) Feed | LinkedIn"), observed(4));
  assert.deepEqual(parseIndicator(linkedin, "Inicio | LinkedIn (6)"), observed(6));
});

test("descarta títulos ausentes, ambiguos o con números de navegación", () => {
  for (const title of [undefined, "Facebook", "(3) WhatsApp", "(2) Contacto | Facebook",
    "Facebook (3) (4)", "(0+) Facebook", "Facebook 2026", "(40000000000) Facebook"]) {
    assert.equal(parseIndicator(facebook, title), null);
  }
});

test("solo consulta pestañas después de comprobar el permiso del origen", async () => {
  const browser = {
    permissions: { contains: async () => false },
    tabs: { query: () => assert.fail("No se debe consultar un origen sin autorización") },
  };
  assert.deepEqual(await readPlatform(instagram, browser), { state: "unauthorized" });
});

test("descarta el resultado si se revoca el permiso durante la consulta", async () => {
  let checks = 0;
  const browser = {
    permissions: { contains: async () => ++checks === 1 },
    tabs: { query: async () => [] },
  };
  assert.deepEqual(await readPlatform(instagram, browser), { state: "unauthorized" });
});

test("distingue falta de pestaña, indicador desconocido y valor observado", async () => {
  let titles = [];
  const browser = {
    permissions: { contains: async () => true },
    tabs: {
      query: async (query) => {
        assert.deepEqual(query, { url: [whatsapp.origin] });
        return titles.map((title) => ({ title }));
      },
    },
  };

  for (const [sample, expected] of [
    [[], { state: "no_tab" }],
    [[undefined], { state: "unknown" }],
    [["WhatsApp"], { state: "unknown" }],
    [["(0) WhatsApp"], { state: "observed", ...observed(0) }],
    [["(2) WhatsApp", "(2) WhatsApp Web"], { state: "observed", ...observed(2) }],
    [["(2) WhatsApp", "(3) WhatsApp"], { state: "unknown" }],
    [["(2) WhatsApp", "WhatsApp"], { state: "unknown" }],
  ]) {
    titles = sample;
    assert.deepEqual(await readPlatform(whatsapp, browser), expected);
  }
});
