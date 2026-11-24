import { platforms } from "./indicators.mjs";

export const MONITORING_KEY = "automaticMonitoring";
const PENDING_KEY = "pendingMonitoringPlatforms";

export function createMonitor(browser) {
  let queue = Promise.resolve();
  let requested;

  function enqueue(task) {
    const job = queue.then(task);
    queue = job.catch(() => {});
    return job;
  }

  async function enabled() {
    const saved = await browser.storage.local.get(MONITORING_KEY);
    return requested !== false && saved[MONITORING_KEY] === true;
  }

  async function openMissing(platform) {
    const origins = [platform.origin];
    if (!(await browser.permissions.contains({ origins }))) return;
    const existing = await browser.tabs.query({ url: origins });
    if (existing.some((tab) => !tab.incognito)) return;

    const url = platform.origin.slice(0, -1);
    const loading = await browser.tabs.query({ status: "loading" });
    if (loading.some((tab) => !tab.incognito && tab.pendingUrl?.startsWith(url))) return;

    const windows = (await browser.windows.getAll({ windowTypes: ["normal"] }))
      .filter((window) => !window.incognito && window.id !== undefined);
    const window = windows.find((item) => item.focused) ?? windows[0];
    if (!window) return platform.id;

    if (await browser.permissions.contains({ origins }) && await enabled()) {
      try {
        await browser.tabs.create({ url, windowId: window.id, active: false });
      } catch (error) {
        // Una ventana puede cerrarse entre la consulta y la creación.
        if (!(await browser.windows.getAll({ windowTypes: ["normal"] }))
          .some((item) => item.id === window.id)) return platform.id;
        throw error;
      }
    }
  }

  async function reconcile(ids) {
    if (!(await enabled())) return;
    const saved = await browser.storage.session.get(PENDING_KEY);
    const wanted = new Set([...(saved[PENDING_KEY] ?? []), ...ids]);
    const pending = [];
    let failure;
    for (const platform of platforms.filter(({ id }) => wanted.has(id))) {
      if (!(await enabled())) return;
      try {
        const deferred = await openMissing(platform);
        if (deferred) pending.push(deferred);
      } catch (error) {
        failure = error;
      }
    }
    await browser.storage.session.set({ [PENDING_KEY]: pending });
    if (failure) throw failure;
  }

  return {
    setEnabled(value) {
      requested = value;
      return enqueue(async () => {
        await browser.storage.local.set({ [MONITORING_KEY]: value });
        if (value) await reconcile(platforms.map(({ id }) => id));
        else await browser.storage.session.remove(PENDING_KEY);
        return value;
      });
    },
    start: () => enqueue(() => reconcile(platforms.map(({ id }) => id))),
    resume: () => enqueue(() => reconcile([])),
    permissionAdded: (origins = []) => enqueue(() =>
      reconcile(platforms.filter(({ origin }) => origins.includes(origin)).map(({ id }) => id))
    ),
  };
}
