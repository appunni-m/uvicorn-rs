#!/usr/bin/env node

import net from "node:net";
import { performance } from "node:perf_hooks";

const args = process.argv.slice(2);
const host = args[0] ?? "127.0.0.1";
const port = Number(args[1] ?? 8000);
const seconds = Number(args[2] ?? 10);
const concurrency = Number(args[3] ?? 64);
const path = args[4] ?? "/";
const expectedBody = Buffer.from(args[5] ?? "Hello World!");
const request = Buffer.from(
  `GET ${path} HTTP/1.1\r\nHost: ${host}:${port}\r\nConnection: keep-alive\r\n\r\n`,
);

class SocketReader {
  constructor(socket) {
    this.socket = socket;
    this.buffer = Buffer.alloc(0);
    this.waiters = [];
    this.error = null;
    socket.on("data", (chunk) => {
      this.buffer = this.buffer.length ? Buffer.concat([this.buffer, chunk]) : chunk;
      this.wake();
    });
    socket.on("error", (error) => {
      this.error = error;
      this.wake();
    });
    socket.on("close", () => {
      if (!this.error) this.error = new Error("socket closed before response completed");
      this.wake();
    });
  }

  wake() {
    for (const resolve of this.waiters.splice(0)) resolve();
  }

  async waitForData() {
    if (this.error) throw this.error;
    await new Promise((resolve) => this.waiters.push(resolve));
    if (this.error) throw this.error;
  }

  async take(length) {
    while (this.buffer.length < length) await this.waitForData();
    const value = this.buffer.subarray(0, length);
    this.buffer = this.buffer.subarray(length);
    return value;
  }

  async until(delimiter) {
    const marker = Buffer.from(delimiter);
    while (true) {
      const index = this.buffer.indexOf(marker);
      if (index >= 0) {
        const value = this.buffer.subarray(0, index);
        this.buffer = this.buffer.subarray(index + marker.length);
        return value;
      }
      await this.waitForData();
    }
  }

  async readResponse() {
    const header = (await this.until("\r\n\r\n")).toString("latin1");
    const lines = header.split("\r\n");
    const status = Number(lines[0].split(" ")[1]);
    const headers = new Map();
    for (const line of lines.slice(1)) {
      const separator = line.indexOf(":");
      if (separator >= 0) {
        headers.set(line.slice(0, separator).trim().toLowerCase(), line.slice(separator + 1).trim());
      }
    }
    let body;
    if (headers.get("transfer-encoding")?.toLowerCase().includes("chunked")) {
      const chunks = [];
      while (true) {
        const sizeLine = (await this.until("\r\n")).toString("ascii").split(";", 1)[0];
        const size = Number.parseInt(sizeLine, 16);
        if (!Number.isFinite(size)) throw new Error(`invalid chunk size ${sizeLine}`);
        if (size === 0) {
          await this.until("\r\n");
          break;
        }
        chunks.push(await this.take(size));
        await this.take(2);
      }
      body = Buffer.concat(chunks);
    } else {
      body = await this.take(Number(headers.get("content-length") ?? 0));
    }
    return { status, body };
  }
}

function connect() {
  return new Promise((resolve, reject) => {
    const socket = net.createConnection({ host, port });
    socket.once("connect", () => resolve(socket));
    socket.once("error", reject);
  });
}

const latencies = [];
let failures = 0;
let firstFailure = null;
const deadline = performance.now() + seconds * 1000;

async function worker() {
  const socket = await connect();
  socket.setNoDelay(true);
  const reader = new SocketReader(socket);
  try {
    while (performance.now() < deadline) {
      const started = performance.now();
      await new Promise((resolve, reject) => {
        socket.write(request, (error) => (error ? reject(error) : resolve()));
      });
      const response = await reader.readResponse();
      latencies.push(performance.now() - started);
      if (response.status !== 200 || !response.body.equals(expectedBody)) {
        failures += 1;
        firstFailure ??= {
          status: response.status,
          body: response.body.toString("hex"),
        };
      }
    }
  } catch (error) {
    failures += 1;
    firstFailure ??= { error: String(error) };
  } finally {
    socket.destroy();
  }
}

await Promise.all(Array.from({ length: concurrency }, worker));
latencies.sort((a, b) => a - b);
const percentile = (p) => latencies[Math.max(0, Math.ceil(p * latencies.length) - 1)] ?? 0;
const elapsed = seconds;
const result = {
  requests: latencies.length,
  duration_seconds: elapsed,
  requests_per_second: latencies.length / elapsed,
  p50_ms: percentile(0.50),
  p95_ms: percentile(0.95),
  p99_ms: percentile(0.99),
  failures,
  first_failure: firstFailure,
};
console.log(JSON.stringify(result));
if (failures > 0 || latencies.length === 0) process.exitCode = 1;
