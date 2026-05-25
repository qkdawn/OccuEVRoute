import { createReadStream, promises as fs } from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const port = Number(process.env.PORT ?? 80);
const backendOrigin = new URL(process.env.BACKEND_ORIGIN ?? "http://backend:8000");
const distDir = path.join(path.dirname(fileURLToPath(import.meta.url)), "dist");

const mimeTypes = new Map([
  [".css", "text/css; charset=utf-8"],
  [".html", "text/html; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".png", "image/png"],
  [".svg", "image/svg+xml"],
  [".webp", "image/webp"],
]);

const server = http.createServer(async (request, response) => {
  if (!request.url) {
    response.writeHead(400).end();
    return;
  }

  const requestUrl = new URL(request.url, `http://${request.headers.host ?? "localhost"}`);
  if (requestUrl.pathname.startsWith("/api/")) {
    proxyApi(request, response, requestUrl);
    return;
  }

  const filePath = await resolveStaticPath(requestUrl.pathname);
  response.setHeader("Cache-Control", filePath.endsWith("index.html") ? "no-cache" : "public, max-age=31536000, immutable");
  response.setHeader("Content-Type", mimeTypes.get(path.extname(filePath)) ?? "application/octet-stream");
  createReadStream(filePath).pipe(response);
});

server.listen(port, "0.0.0.0");

function proxyApi(request, response, requestUrl) {
  const target = new URL(`${requestUrl.pathname}${requestUrl.search}`, backendOrigin);
  const proxyRequest = http.request(
    target,
    {
      headers: { ...request.headers, host: backendOrigin.host },
      method: request.method,
    },
    (proxyResponse) => {
      response.writeHead(proxyResponse.statusCode ?? 502, proxyResponse.headers);
      proxyResponse.pipe(response);
    },
  );
  proxyRequest.on("error", () => {
    response.writeHead(502, { "Content-Type": "application/json; charset=utf-8" });
    response.end(JSON.stringify({ detail: "Backend service is unavailable." }));
  });
  request.pipe(proxyRequest);
}

async function resolveStaticPath(urlPath) {
  const cleanPath = decodeURIComponent(urlPath.split("?")[0] ?? "/");
  const requestedPath = path.normalize(path.join(distDir, cleanPath));
  if (!requestedPath.startsWith(distDir)) return path.join(distDir, "index.html");
  try {
    const stat = await fs.stat(requestedPath);
    if (stat.isFile()) return requestedPath;
  } catch {
    return path.join(distDir, "index.html");
  }
  return path.join(distDir, "index.html");
}
