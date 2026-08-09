import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, join, normalize, resolve, sep } from "node:path";

import app from "../dist/server/server.js";

const host = process.env["HOST"] ?? "0.0.0.0";
const port = Number(process.env["PORT"] ?? "3000");
const apiProxyTarget = process.env["VITE_API_PROXY_TARGET"] ?? "http://127.0.0.1:8000";
const clientRoot = resolve("dist/client");

const contentTypes = new Map([
  [".css", "text/css; charset=utf-8"],
  [".html", "text/html; charset=utf-8"],
  [".ico", "image/x-icon"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".png", "image/png"],
  [".svg", "image/svg+xml"],
  [".txt", "text/plain; charset=utf-8"],
  [".webp", "image/webp"],
]);

function staticPath(url) {
  const pathname = new URL(url, "http://localhost").pathname;
  const decoded = decodeURIComponent(pathname);
  const candidate = normalize(join(clientRoot, decoded));
  return candidate === clientRoot || candidate.startsWith(`${clientRoot}${sep}`) ? candidate : null;
}

async function sendStatic(request, response) {
  const filePath = staticPath(request.url ?? "/");
  if (!filePath) return false;
  const info = await stat(filePath).catch(() => undefined);
  if (!info?.isFile()) return false;

  response.writeHead(200, {
    "content-length": String(info.size),
    "content-type": contentTypes.get(extname(filePath)) ?? "application/octet-stream",
  });
  createReadStream(filePath).pipe(response);
  return true;
}

async function sendApp(request, response) {
  const url = `http://${request.headers.host ?? "localhost"}${request.url ?? "/"}`;
  const appResponse = await app.fetch(new Request(url, { method: request.method }), {}, {});
  response.writeHead(appResponse.status, Object.fromEntries(appResponse.headers));
  response.end(Buffer.from(await appResponse.arrayBuffer()));
}

async function proxyApi(request, response) {
  const requestUrl = new URL(request.url ?? "/", `http://${request.headers.host ?? "localhost"}`);
  if (!requestUrl.pathname.startsWith("/api")) return false;

  const targetUrl = new URL(
    requestUrl.pathname.replace(/^\/api/, "") + requestUrl.search,
    apiProxyTarget,
  );
  const body =
    request.method === "GET" || request.method === "HEAD"
      ? undefined
      : await readRequestBody(request);
  const headers = new Headers();
  for (const [key, value] of Object.entries(request.headers)) {
    if (value && !["connection", "host", "content-length"].includes(key.toLowerCase())) {
      headers.set(key, Array.isArray(value) ? value.join(",") : value);
    }
  }

  const proxied = await fetch(targetUrl, { method: request.method, headers, body });
  response.writeHead(proxied.status, Object.fromEntries(proxied.headers));
  response.end(Buffer.from(await proxied.arrayBuffer()));
  return true;
}

async function readRequestBody(request) {
  const chunks = [];
  for await (const chunk of request) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }
  return Buffer.concat(chunks);
}

createServer(async (request, response) => {
  try {
    if (await proxyApi(request, response)) return;
    if (request.method === "GET" || request.method === "HEAD") {
      if (await sendStatic(request, response)) return;
    }
    await sendApp(request, response);
  } catch (error) {
    console.error(error);
    response.writeHead(500, { "content-type": "text/plain; charset=utf-8" });
    response.end("Internal Server Error");
  }
}).listen(port, host, () => {
  console.log(`Frontend listening on http://${host}:${port}`);
});
