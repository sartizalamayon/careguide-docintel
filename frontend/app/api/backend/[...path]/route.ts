/**
 * Server-side proxy: browser -> /api/backend/<path> -> FastAPI /api/v1/<path>.
 * Adds X-API-Key on the server so the key never reaches the browser. Streams bodies both ways
 * (multipart uploads, PDFs, page images).
 */
import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000/api/v1";
const API_KEY = process.env.API_KEY ?? "";
const FORWARD_REQ_HEADERS = ["content-type", "accept", "content-length"];
const FORWARD_RES_HEADERS = ["content-type", "content-disposition", "cache-control", "content-length"];

async function proxy(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  if (path.some((p) => p === ".." || p.includes("/"))) {
    return Response.json({ error: { code: "BAD_PATH", message: "Invalid path" } }, { status: 400 });
  }
  const url = `${BACKEND_URL}/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;
  const headers = new Headers({ "X-API-Key": API_KEY });
  for (const h of FORWARD_REQ_HEADERS) {
    const v = req.headers.get(h);
    if (v) headers.set(h, v);
  }
  const hasBody = !["GET", "HEAD"].includes(req.method);
  let res: Response;
  try {
    res = await fetch(url, {
      method: req.method,
      headers,
      body: hasBody ? req.body : undefined,
      // @ts-expect-error - required by Node fetch when streaming a request body
      duplex: hasBody ? "half" : undefined,
      cache: "no-store",
    });
  } catch {
    return Response.json({ error: { code: "BACKEND_UNREACHABLE", message: "The API is not reachable." } }, { status: 502 });
  }
  const out = new Headers();
  for (const h of FORWARD_RES_HEADERS) {
    const v = res.headers.get(h);
    if (v) out.set(h, v);
  }
  return new Response(res.body, { status: res.status, headers: out });
}

export { proxy as GET, proxy as POST, proxy as PATCH, proxy as DELETE };
