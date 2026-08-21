import { getJson, postJson, } from "../../shared/api/apiClient.js";
const AUTH_BASE = "/api/auth";
export function getOperatorSession(options) {
    return getJson(`${AUTH_BASE}/session`, options);
}
export function loginOperatorSession(body, options) {
    return postJson(`${AUTH_BASE}/login`, body, options);
}
export function registerOperatorSession(body, options) {
    return postJson(`${AUTH_BASE}/register`, body, options);
}
export function logoutOperatorSession(options) {
    return postJson(`${AUTH_BASE}/logout`, {}, options);
}
