import { platforms, readPlatform } from "./indicators.mjs";

export function createSynchronizer(browser, clock = () => new Date()) {
  let previous = null;
  let queue = Promise.resolve();
  let automatic = null;

  async function publish(force) {
    const updated_at = clock().toISOString();
    const indicators = await Promise.all(platforms.map(async (platform) => {
      const result = await readPlatform(platform, browser).catch(() => ({ state: "unavailable" }));
      return {
        platform: platform.id,
        value: result.value ?? null,
        state: result.lowerBound ? "lower_bound" : result.state,
      };
    }));
    const signature = JSON.stringify(indicators);
    if (!force && signature === previous) return { indicators, connected: true };

    const snapshot = indicators.map((row) => ({ ...row, updated_at }));
    let connected = false;
    try {
      const response = await browser.runtime.sendNativeMessage("com.moona.connect", {
        indicators: snapshot,
      });
      connected = response?.ok === true;
    } catch {
      // La vista local de Chrome sigue funcionando aunque falte el host.
    }
    previous = connected ? signature : null;
    return { indicators, connected };
  }

  return function sync(force = false) {
    if (!force && automatic) return automatic;
    const job = queue.then(() => {
      // Permite encolar otra lectura si una pestaña cambia durante esta consulta.
      if (automatic === job) automatic = null;
      return publish(force);
    });
    queue = job.catch(() => {});
    if (!force) automatic = job;
    return job;
  };
}
