const API_BASE = "/api";

export async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    }
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : body.detail?.message;
    throw new Error(detail || body.message || `Permintaan gagal (${response.status})`);
  }
  return body;
}
