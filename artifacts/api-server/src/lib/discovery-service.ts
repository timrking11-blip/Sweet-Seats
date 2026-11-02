import { spawn } from "node:child_process";
import { request } from "node:http";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { RequestHandler } from "express";
import { logger } from "./logger";

let socketPath: string;

/** Preserve the imported Python service rather than reimplementing its data rules. */
export async function startDiscoveryService() {
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
  const directory = await mkdtemp(path.join(tmpdir(), "sweet-seats-"));
  socketPath = path.join(directory, "api.sock");
  const child = spawn("uv", [
    "run", "--frozen", "python", "-m", "services.api.replit_server",
    "--socket", socketPath,
  ], { cwd: root, stdio: ["ignore", "inherit", "inherit"] });
  let exited = false;
  let stopping = false;
  child.on("error", () => { exited = true; });
  child.on("exit", () => {
    exited = true;
    if (!stopping) {
      logger.error("Original discovery service stopped");
      process.exit(1);
    }
  });
  const stop = () => {
    stopping = true;
    child.kill("SIGTERM");
    void rm(directory, { recursive: true, force: true });
  };
  process.once("exit", stop);
  for (const signal of ["SIGTERM", "SIGINT"] as const) {
    process.once(signal, () => { stop(); process.exit(0); });
  }
  for (let attempt = 0; attempt < 150; attempt++) {
    if (exited) throw new Error("Discovery service failed to start");
    const healthy = await new Promise<boolean>((resolve) => {
      const req = request({ socketPath, path: "/health", timeout: 500 }, (res) => {
        res.resume();
        resolve(res.statusCode === 200);
      });
      req.on("error", () => resolve(false));
      req.on("timeout", () => { req.destroy(); resolve(false); });
      req.end();
    });
    if (healthy) return;
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  stop();
  throw new Error("Discovery service startup timed out");
}

export const discoveryProxy: RequestHandler = (req, res) => {
  const upstreamPath = req.originalUrl.startsWith("/api/discovery/")
    ? req.originalUrl.replace(/^\/api\/discovery/, "/v1")
    : req.originalUrl.replace(/^\/api/, "");
  const headers = { ...req.headers };
  delete headers.host;
  delete headers.connection;
  const upstream = request({
    socketPath, path: upstreamPath, method: req.method, headers, timeout: 15000,
  }, (response) => {
    res.status(response.statusCode ?? 502);
    for (const [key, value] of Object.entries(response.headers)) {
      if (value !== undefined && !["connection", "transfer-encoding"].includes(key)) {
        res.setHeader(key, value);
      }
    }
    response.pipe(res);
  });
  upstream.on("timeout", () => upstream.destroy(new Error("API timeout")));
  upstream.on("error", () => {
    if (!res.headersSent) {
      res.status(503).set("Cache-Control", "no-store").json({ detail: "Discovery service unavailable." });
    } else res.destroy();
  });
  req.on("aborted", () => upstream.destroy());
  req.pipe(upstream);
};
