const hiddenPilotPaths = new Set(["/markets", "/files", "/reports", "/settings", "/bot-connections"]);

export const pilotCapabilities = Object.freeze({
  visibleModules: ["dashboard", "products", "templates", "campaigns", "preview", "export", "history", "account"],
  hiddenModules: ["markets", "files", "reports", "settings", "bot-connections"],
});

export function canAccessPilotPath(path) {
  return ![...hiddenPilotPaths].some((hiddenPath) => path === hiddenPath || path.startsWith(`${hiddenPath}/`));
}
