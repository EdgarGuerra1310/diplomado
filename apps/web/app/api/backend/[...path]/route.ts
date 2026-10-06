import { NextRequest, NextResponse } from "next/server";

const backend = process.env.API_INTERNAL_URL ?? "http://localhost:8000/api/v1";

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const target = `${backend}/${path.join("/")}${request.nextUrl.search}`;
  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  const response = await fetch(target, {
    method: request.method,
    headers: {
      "Content-Type": request.headers.get("content-type") ?? "application/json",
      ...(request.headers.get("range") ? { Range: request.headers.get("range") as string } : {}),
    },
    body: hasBody ? await request.text() : undefined,
    cache: "no-store",
  });
  const headers = new Headers();
  for (const name of ["content-type", "content-length", "content-range", "accept-ranges", "content-disposition", "last-modified"]) {
    const value = response.headers.get(name);
    if (value) headers.set(name, value);
  }
  return new NextResponse(response.body, {
    status: response.status,
    headers,
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;
