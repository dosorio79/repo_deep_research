import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import { createServer, request as httpRequest } from "node:http";
import { request as httpsRequest } from "node:https";
import { extname, join, normalize, resolve, sep } from "node:path";

import app from "../dist/server/server.js";

const host = process.env["HOST"] ?? "0.0.0.0";
const port = Number(process.env["PORT"] ?? "3000");
const apiProxyTarget = process.env["VITE_API_PROXY_TARGET"] ?? "http://127.0.0.1:8000";
const clientRoot = resolve("dist/client");
const proxyConnectTimeoutMs = 15000;

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
  const headers = {};
  for (const [key, value] of Object.entries(request.headers)) {
    if (value && !["connection", "host", "content-length"].includes(key.toLowerCase())) {
      headers[key] = value;
    }
  }

  await new Promise((resolve, reject) => {
    const client = targetUrl.protocol === "https:" ? httpsRequest : httpRequest;
    let clientClosed = false;
    let upstreamEnded = false;
    const connectTimeout = setTimeout(() => {
      upstream.destroy(new Error(`Timed out connecting to API target ${apiProxyTarget}`));
    }, proxyConnectTimeoutMs);
    const clearConnectTimeout = () => clearTimeout(connectTimeout);
    const upstream = client(
      targetUrl,
      {
        method: request.method,
        headers,
        timeout: 0,
      },
      (upstreamResponse) => {
        clearConnectTimeout();
        response.writeHead(upstreamResponse.statusCode ?? 502, upstreamResponse.headers);
        upstreamResponse.pipe(response);
        upstreamResponse.on("end", () => {
          upstreamEnded = true;
          resolve();
        });
      },
    );
    upstream.on("socket", (socket) => {
      if (socket.connecting) {
        socket.once("connect", clearConnectTimeout);
      } else {
        clearConnectTimeout();
      }
    });
    upstream.on("error", (error) => {
      clearConnectTimeout();
      if (clientClosed) {
        resolve();
        return;
      }
      reject(error);
    });
    response.on("close", () => {
      if (!upstreamEnded) {
        clientClosed = true;
        upstream.destroy();
      }
    });
    request.pipe(upstream);
  });
  return true;
}

const server = createServer(async (request, response) => {
  try {
    if (await proxyApi(request, response)) return;
    if (request.method === "GET" || request.method === "HEAD") {
      if (await sendStatic(request, response)) return;
    }
    await sendApp(request, response);
  } catch (error) {
    console.error(error);
    if (!response.headersSent && !response.destroyed) {
      response.writeHead(502, { "content-type": "application/json; charset=utf-8" });
      response.end(
        JSON.stringify({
          detail:
            "Frontend proxy could not reach the API service. Check that the API container is running and healthy.",
        }),
      );
    } else if (!response.destroyed) {
      response.end();
    }
  }
});

server.requestTimeout = 0;
server.headersTimeout = 0;
server.keepAliveTimeout = 0;

server.listen(port, host, () => {
  console.log(`Frontend listening on http://${host}:${port}`);
});
