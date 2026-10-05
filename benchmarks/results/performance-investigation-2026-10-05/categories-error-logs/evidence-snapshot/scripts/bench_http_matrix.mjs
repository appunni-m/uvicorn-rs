#!/usr/bin/env node

import http from "node:http";
import { performance } from "node:perf_hooks";

const config = JSON.parse(process.argv[2] ?? "{}");
const host = config.host ?? "127.0.0.1";
const port = Number(config.port ?? 8000);
const seconds = Number(config.seconds ?? 5);
const concurrency = Number(config.concurrency ?? 64);
const path = config.path ?? "/fixed";
const mode = config.mode ?? "fixed";
const uploadBytes = Number(config.upload_bytes ?? 0);
const uploadChunkBytes = Number(config.upload_chunk_bytes ?? (uploadBytes || 1));
const uploadDelayMs = Number(config.upload_delay_ms ?? 0);
const readDelayMs = Number(config.read_delay_ms ?? 0);
const readRateBytesPerSecond = Number(config.read_rate_bytes_per_second ?? 0);
const expectedStatus = Number(config.expected_status ?? 200);
const maxRequests = Number(config.max_requests ?? 0);
if (!Number.isFinite(readRateBytesPerSecond) || readRateBytesPerSecond < 0) {
  throw new Error("read_rate_bytes_per_second must be finite and nonnegative");
}

function expectedBody() {
  if (typeof config.expected_body === "string") return Buffer.from(config.expected_body);
  if (mode === "upload") return Buffer.from(`bytes=${uploadBytes}`);
  if (mode === "scope") return Buffer.from("scope-ok");
  if (mode === "context") return Buffer.from("request-context");
  if (mode === "exception") return Buffer.from("Internal Server Error");
  return Buffer.from("Hello World!");
}

const wantedBody = expectedBody();
const responseBytes = Number(config.response_bytes ?? 0);
const responseFillByte = Number(config.response_fill_byte ?? 0x78);
const largeExpectedBody = responseBytes > 0 ? Buffer.alloc(responseBytes, responseFillByte) : null;

const headers = Object.fromEntries(config.headers ?? []);
if (mode === "upload") headers["content-length"] = String(uploadBytes);
const uploadBody = mode === "upload" ? Buffer.alloc(uploadBytes, 0x61) : Buffer.alloc(0);
const startedAt = performance.now();
const deadline = startedAt + seconds * 1000;
const latencies = [];
let failures = 0;
let firstFailure = null;
let bytesSent = 0;
let bytesReceived = 0;
let allocatedRequests = 0;

function requestOne(agent) {
  const requestStarted = performance.now();
  return new Promise((resolve, reject) => {
    let settled = false;
    let resumeTimer;
    let completionTimer;
    function fail(error) {
      if (settled) return;
      settled = true;
      clearTimeout(resumeTimer);
      clearTimeout(completionTimer);
      reject(error);
    }
    const request = http.request(
      {
        host,
        port,
        path,
        method: mode === "upload" ? "POST" : "GET",
        headers,
        agent,
      },
      (response) => {
        const chunks = largeExpectedBody === null ? [] : null;
        let bodyValid = true;
        let bodyLength = 0;
        const pacingStartedAt = performance.now();
        function pacingDelay() {
          return readRateBytesPerSecond > 0
            ? Math.max(0, pacingStartedAt + (bodyLength / readRateBytesPerSecond) * 1000 - performance.now())
            : 0;
        }
        function complete() {
          if (settled) return;
          // The end event can follow the final data event before its pause
          // finishes. Include the last bytes in the paced completion boundary.
          const remaining = pacingDelay();
          if (remaining > 0) {
            completionTimer = setTimeout(complete, remaining);
            return;
          }
          settled = true;
          clearTimeout(resumeTimer);
          resolve({
            status: response.statusCode,
            bodyLength,
            bodyValid,
            latencyMs: performance.now() - requestStarted,
          });
        }
        response.on("data", (chunk) => {
          if (settled) return;
          if (largeExpectedBody) {
            const expectedChunk = largeExpectedBody.subarray(bodyLength, bodyLength + chunk.length);
            if (expectedChunk.length !== chunk.length || !expectedChunk.equals(chunk)) bodyValid = false;
          } else {
            chunks.push(chunk);
          }
          bodyLength += chunk.length;
          bytesReceived += chunk.length;
          // Cumulative byte pacing gives both servers the same drain rate,
          // regardless of TCP segmentation or the number of data callbacks.
          const delay = readRateBytesPerSecond > 0 ? pacingDelay() : readDelayMs;
          if (delay > 0) {
            response.pause();
            clearTimeout(resumeTimer);
            resumeTimer = setTimeout(() => {
              if (!settled) response.resume();
            }, delay);
          }
        });
        response.on("error", fail);
        response.on("end", () => {
          if (largeExpectedBody) {
            bodyValid = bodyValid && bodyLength === responseBytes;
          } else {
            bodyValid = Buffer.concat(chunks).equals(wantedBody);
          }
          complete();
        });
      },
    );
    request.on("error", fail);

    (async () => {
      try {
        if (uploadBytes > 0) {
          for (let offset = 0; offset < uploadBytes; offset += uploadChunkBytes) {
            const chunk = uploadBody.subarray(offset, Math.min(offset + uploadChunkBytes, uploadBytes));
            request.write(chunk);
            bytesSent += chunk.length;
            if (uploadDelayMs > 0) {
              await new Promise((resolveDelay) => setTimeout(resolveDelay, uploadDelayMs));
            }
          }
        }
        request.end();
      } catch (error) {
        request.destroy(error);
        fail(error);
      }
    })();
  });
}

async function worker() {
  const agent = new http.Agent({ keepAlive: true, maxSockets: 1 });
  try {
    while (performance.now() < deadline) {
      if (maxRequests > 0 && allocatedRequests >= maxRequests) break;
      // Reserve before the first await so concurrent workers cannot exceed
      // the input's cap. Completed requests remain counted by latencies.
      allocatedRequests += 1;
      try {
        const response = await requestOne(agent);
        latencies.push(response.latencyMs);
        if (response.status !== expectedStatus || !response.bodyValid) {
          failures += 1;
          firstFailure ??= {
            status: response.status,
            body_bytes: response.bodyLength,
            expected_body_bytes: largeExpectedBody === null ? wantedBody.length : responseBytes,
            body_valid: response.bodyValid,
          };
        }
      } catch (error) {
        failures += 1;
        firstFailure ??= { error: String(error) };
        break;
      }
    }
  } finally {
    agent.destroy();
  }
}

await Promise.all(Array.from({ length: concurrency }, worker));
const elapsedSeconds = (performance.now() - startedAt) / 1000;
latencies.sort((a, b) => a - b);
const percentile = (p) => latencies[Math.max(0, Math.ceil(p * latencies.length) - 1)] ?? 0;
const result = {
  requests: latencies.length,
  duration_seconds: elapsedSeconds,
  requests_per_second: latencies.length / elapsedSeconds,
  request_body_bytes: bytesSent,
  response_body_bytes: bytesReceived,
  application_bytes_per_second: (bytesSent + bytesReceived) / elapsedSeconds,
  p50_ms: percentile(0.5),
  p95_ms: percentile(0.95),
  p99_ms: percentile(0.99),
  failures,
  first_failure: firstFailure,
};
console.log(JSON.stringify(result));
if (failures > 0 || latencies.length === 0) process.exitCode = 1;
