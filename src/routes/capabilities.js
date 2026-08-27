const hiddenPilotPaths = new Set(["/markets", "/files", "/reports", "/settings", "/bot-connections"]);

// Billing is kept explicitly visible for compatibility with existing direct links.
const explicitlyVisiblePilotPaths = new Set(["/settings", "/settings/billing"]);

export const pilotCapabilities = Object.freeze({
  visibleModules: ["dashboard", "products", "templates", "campaigns", "preview", "export", "history", "account"],
  hiddenModules: ["markets", "files", "reports", "settings", "bot-connections"],
});

export function canAccessPilotPath(path) {
  if (explicitlyVisiblePilotPaths.has(path)) return true;
  return ![...hiddenPilotPaths].some((hiddenPath) => path === hiddenPath || path.startsWith(`${hiddenPath}/`));
}
