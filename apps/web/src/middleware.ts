import { NextRequest, NextResponse } from "next/server";

// Server Components fetch the backend directly with the session cookie
// (see lib/api.ts authHeader()) and throw loudly on failure now that demo
// data no longer silently fills the gap -- so a visitor with no session
// hitting a protected page crashed with a raw 500 instead of being sent to
// log in. This is the redirect that should have caught that before it ever
// reached the page.
const PUBLIC_PATHS = ["/login", "/submit"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (PUBLIC_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`))) {
    return NextResponse.next();
  }
  const token = request.cookies.get("notamsys_access")?.value;
  if (!token) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"]
};
