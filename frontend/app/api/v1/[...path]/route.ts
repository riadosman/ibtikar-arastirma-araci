import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  if (
    path.some(
      (segment) => segment === "." || segment === ".." || segment.includes("/"),
    )
  ) {
    return Response.json({ detail: "Invalid API path." }, { status: 400 });
  }
  if (!["GET", "HEAD"].includes(request.method)) {
    const origin = request.headers.get("origin");
    if (origin && new URL(origin).host !== request.headers.get("host")) {
      return Response.json(
        { detail: "Cross-origin requests are not allowed." },
        { status: 403 },
      );
    }
  }
  const headers = new Headers();
  for (const name of [
    "content-type",
    "cookie",
    "authorization",
    "x-requested-with",
  ]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  try {
    const upstream = await fetch(
      `${process.env.BACKEND_URL || "http://127.0.0.1:8000"}/api/v1/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`,
      {
        method: request.method,
        headers,
        body: ["GET", "HEAD"].includes(request.method)
          ? undefined
          : await request.arrayBuffer(),
        cache: "no-store",
        redirect: "manual",
        signal: AbortSignal.timeout(60000),
      },
    );
    const output = new Headers();
    for (const name of [
      "content-type",
      "content-disposition",
      "x-request-id",
      "retry-after",
    ]) {
      const value = upstream.headers.get(name);
      if (value) output.set(name, value);
    }
    for (const cookie of upstream.headers.getSetCookie())
      output.append("set-cookie", cookie);
    output.set("cache-control", "no-store");
    return new Response(upstream.body, {
      status: upstream.status,
      headers: output,
    });
  } catch {
    return Response.json(
      { detail: "Unable to reach the server. Please try again." },
      { status: 502 },
    );
  }
}
export { proxy as GET, proxy as POST, proxy as PATCH, proxy as DELETE };
