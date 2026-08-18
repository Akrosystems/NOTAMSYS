// Shared by middleware.ts (Edge runtime) and the authenticated BFF proxy
// (Node runtime) -- both need to silently exchange a still-valid refresh
// token for a new access token instead of just failing the request. Kept
// to Web-standard APIs (fetch) so it works in either runtime.

const API_URL = process.env.INTERNAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export async function refreshAccessToken(refreshToken: string): Promise<string | null> {
  try {
    const response = await fetch(`${API_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
      cache: "no-store",
    });
    if (!response.ok) return null;
    const data = await response.json();
    return typeof data.access_token === "string" ? data.access_token : null;
  } catch {
    return null;
  }
}

// Mirrors the login route's own cookie options exactly (apps/web/src/app/api/auth/login/route.ts)
// -- a refreshed token must behave identically to a freshly-issued one.
export const ACCESS_COOKIE_OPTIONS = {
  httpOnly: true,
  secure: process.env.NODE_ENV === "production",
  sameSite: "strict" as const,
  path: "/",
  maxAge: 30 * 60,
};
