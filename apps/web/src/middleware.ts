import { NextRequest, NextResponse } from "next/server";
import { ACCESS_COOKIE_OPTIONS, refreshAccessToken } from "@/lib/session-refresh";

// Server Components fetch the backend directly with the session cookie
// (see lib/api.ts authHeader()) and throw loudly on failure now that demo
// data no longer silently fills the gap -- so a visitor with no session
// hitting a protected page crashed with a raw 500 instead of being sent to
// log in. This is the redirect that should have caught that before it ever
// reached the page.
const PUBLIC_PATHS = ["/login", "/submit"];

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (PUBLIC_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`))) {
    return NextResponse.next();
  }
  const token = request.cookies.get("notamsys_access")?.value;
  if (token) return NextResponse.next();

  // No access token doesn't necessarily mean "never logged in" -- the
  // access cookie hard-expires after 30 minutes (access_token_minutes) with
  // no renewal, which used to just silently bounce every visitor back to
  // /login with no explanation the moment that happened, active session or
  // not. The refresh cookie lives for 7 days; if it's still good, mint a
  // fresh access token here and let the request continue as if nothing
  // happened -- no redirect, no flicker, and downstream Server Components
  // (which read the cookie themselves) need to see the new value too, not
  // just the browser on its next request.
  const refreshToken = request.cookies.get("notamsys_refresh")?.value;
  if (refreshToken) {
    const newAccessToken = await refreshAccessToken(refreshToken);
    if (newAccessToken) {
      request.cookies.set("notamsys_access", newAccessToken);
      const response = NextResponse.next({ request });
      response.cookies.set("notamsys_access", newAccessToken, ACCESS_COOKIE_OPTIONS);
      return response;
    }
  }

  const url = request.nextUrl.clone();
  url.pathname = "/login";
  url.searchParams.set("next", pathname);
  // Only claim "your session expired" when there actually was a refresh
  // token that turned out to be no good (genuine expiry/revocation) -- a
  // visitor with no cookies at all was simply never logged in, and telling
  // them their session expired would be wrong.
  if (refreshToken) url.searchParams.set("reason", "expired");
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"]
};
