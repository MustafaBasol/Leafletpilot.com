import { demoMarketId, isRealApiEnabled } from "./config.js";

const TOKEN_KEY = "leafletpilot_access_token";
const MARKET_KEY = "leafletpilot_selected_market_id";
const MARKETS_KEY = "leafletpilot_markets";
const USER_KEY = "leafletpilot_user";

export function getAccessToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function getSelectedMarketId() {
  if (!isRealApiEnabled) return demoMarketId;
  return localStorage.getItem(MARKET_KEY) || "";
}

export function getStoredMarkets() {
  try {
    return JSON.parse(localStorage.getItem(MARKETS_KEY) || "[]");
  } catch {
    return [];
  }
}

export function saveAuthSession({ access_token: accessToken, user, markets }) {
  if (accessToken) localStorage.setItem(TOKEN_KEY, accessToken);
  if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
  const marketList = Array.isArray(markets) ? markets : [];
  localStorage.setItem(MARKETS_KEY, JSON.stringify(marketList));
  const selectedMarketId = marketList[0]?.id || "";
  if (selectedMarketId) {
    localStorage.setItem(MARKET_KEY, selectedMarketId);
  } else {
    localStorage.removeItem(MARKET_KEY);
  }
}

export function clearAuthSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(MARKET_KEY);
  localStorage.removeItem(MARKETS_KEY);
  localStorage.removeItem(USER_KEY);
}

export function hasStoredAuthSession() {
  return Boolean(getAccessToken());
}
