const hiddenPilotPaths = new Set(["/markets", "/files", "/reports", "/settings", "/bot-connections"]);

// Explicit exceptions to the hidden-path rule above: a descendant path that
// must stay reachable even though its parent (here "/settings") is hidden.
const explicitlyVisiblePilotPaths = new Set(["/settings/billing"]);

export const pilotCapabilities = Object.freeze({
  visibleModules: ["dashboard", "products", "templates", "campaigns", "preview", "export", "history", "account"],
  hiddenModules: ["markets", "files", "reports", "settings", "bot-connections"],
});

export function canAccessPilotPath(path) {
  if (explicitlyVisiblePilotPaths.has(path)) return true;
  return ![...hiddenPilotPaths].some((hiddenPath) => path === hiddenPath || path.startsWith(`${hiddenPath}/`));
}
