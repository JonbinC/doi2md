export function rewriteManifestForDistribution(manifest) {
  const clone = structuredClone(manifest);

  if (clone.background?.service_worker) {
    clone.background.service_worker = stripDistPrefix(clone.background.service_worker);
  }

  if (clone.action?.default_popup) {
    clone.action.default_popup = stripDistPrefix(clone.action.default_popup);
  }

  if (clone.options_page) {
    clone.options_page = stripDistPrefix(clone.options_page);
  }

  if (clone.content_scripts) {
    clone.content_scripts = clone.content_scripts.map((script) => ({
      ...script,
      js: Array.isArray(script.js) ? script.js.map(stripDistPrefix) : script.js,
    }));
  }

  if (clone.icons) {
    clone.icons = Object.fromEntries(
      Object.entries(clone.icons).map(([size, path]) => [size, stripDistPrefix(path)])
    );
  }

  if (clone.action?.default_icon) {
    clone.action.default_icon = Object.fromEntries(
      Object.entries(clone.action.default_icon).map(([size, path]) => [size, stripDistPrefix(path)])
    );
  }

  return clone;
}

function stripDistPrefix(path) {
  return String(path || "").replace(/^dist\//, "");
}
