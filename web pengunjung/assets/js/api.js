export async function requestJson(path, options = {}) {
  const response = await fetch(path, { cache: "no-store", ...options });
  let data = {};
  try {
    data = await response.json();
  } catch {
    if (response.ok) throw new Error("Server mengembalikan respons yang tidak dapat dibaca.");
  }
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : "";
    const error = new Error(detail || `Permintaan gagal (${response.status}).`);
    error.status = response.status;
    error.retryAfter = Number(response.headers.get("Retry-After") || 0);
    throw error;
  }
  return data;
}

export function authHeaders(token) {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function postJson(path, body, token, extraHeaders = {}, signal) {
  return requestJson(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token), ...extraHeaders },
    body: JSON.stringify(body ?? {}),
    signal
  });
}
