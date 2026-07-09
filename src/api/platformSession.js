const PLATFORM_TOKEN_KEY = "leafletpilot_platform_access_token";
const PLATFORM_ADMIN_KEY = "leafletpilot_platform_admin";

export function getPlatformAccessToken() {
  return sessionStorage.getItem(PLATFORM_TOKEN_KEY) || "";
}

export function getStoredPlatformAdmin() {
  try {
    return JSON.parse(sessionStorage.getItem(PLATFORM_ADMIN_KEY) || "null");
  } catch {
    return null;
  }
}

export function savePlatformSession({ access_token: accessToken, admin }) {
  if (accessToken) sessionStorage.setItem(PLATFORM_TOKEN_KEY, accessToken);
  if (admin) sessionStorage.setItem(PLATFORM_ADMIN_KEY, JSON.stringify(admin));
}

export function clearPlatformSession() {
  sessionStorage.removeItem(PLATFORM_TOKEN_KEY);
  sessionStorage.removeItem(PLATFORM_ADMIN_KEY);
}

export function hasPlatformSession() {
  return Boolean(getPlatformAccessToken());
}
