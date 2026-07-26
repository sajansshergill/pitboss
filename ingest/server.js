"use strict";

/**
 * PitBoss ingestion service — the Node.js edge of the pipeline.
 *
 * Two modes, one validation path:
 *   HTTP:   node server.js                      -> POST /events, GET /health
 *   Batch:  node server.js --batch <file.jsonl> -> validate a raw firehose file
 *
 * Valid events are appended to data/landing/, rejects go to data/quarantine/
 * with their validation errors attached. Nothing malformed reaches downstream.
 */

const fs = require("fs");
const path = require("path");
const { validateEvent } = require("./schema");

const ROOT = path.resolve(__dirname, "..");
const LANDING_DIR = path.join(ROOT, "data", "landing");
const QUARANTINE_DIR = path.join(ROOT, "data", "quarantine");

function ensureDirs() {
  for (const d of [LANDING_DIR, QUARANTINE_DIR]) {
    fs.mkdirSync(d, { recursive: true });
  }
}

function stamp() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

/**
 * Partition a batch of events into accepted / rejected and write each to its
 * destination. Returns counts. Shared by both HTTP and batch modes.
 */
function processBatch(events) {
  ensureDirs();
  const accepted = [];
  const rejected = [];

  for (const evt of events) {
    const { valid, errors } = validateEvent(evt);
    if (valid) {
      accepted.push(evt);
    } else {
      rejected.push({ event: evt, errors });
    }
  }

  const suffix = stamp();
  if (accepted.length) {
    const f = path.join(LANDING_DIR, `events-${suffix}.jsonl`);
    fs.writeFileSync(f, accepted.map((e) => JSON.stringify(e)).join("\n") + "\n");
  }
  if (rejected.length) {
    const f = path.join(QUARANTINE_DIR, `rejects-${suffix}.jsonl`);
    fs.writeFileSync(f, rejected.map((r) => JSON.stringify(r)).join("\n") + "\n");
  }

  return { accepted: accepted.length, rejected: rejected.length };
}

function runBatch(file) {
  const lines = fs
    .readFileSync(file, "utf8")
    .split("\n")
    .filter((l) => l.trim().length > 0);
  const events = lines.map((l) => {
    try {
      return JSON.parse(l);
    } catch {
      return { __unparseable: l };
    }
  });
  const result = processBatch(events);
  console.log(
    `batch: ${events.length} in -> ${result.accepted} accepted, ` +
      `${result.rejected} quarantined`
  );
}

async function runServer() {
  // Fastify is optional; fall back to core http so the service runs anywhere.
  let fastify;
  try {
    fastify = require("fastify")({ logger: true });
  } catch {
    return runHttpFallback();
  }

  fastify.get("/health", async () => ({ status: "ok", service: "pitboss-ingest" }));

  fastify.post("/events", async (request, reply) => {
    const body = request.body || {};
    const events = Array.isArray(body.events) ? body.events : [body];
    const result = processBatch(events);
    reply.code(result.rejected ? 207 : 200);
    return result;
  });

  const port = process.env.PORT || 8080;
  await fastify.listen({ port, host: "0.0.0.0" });
}

function runHttpFallback() {
  const http = require("http");
  const port = process.env.PORT || 8080;
  const server = http.createServer((req, res) => {
    if (req.method === "GET" && req.url === "/health") {
      res.writeHead(200, { "Content-Type": "application/json" });
      return res.end(JSON.stringify({ status: "ok", service: "pitboss-ingest" }));
    }
    if (req.method === "POST" && req.url === "/events") {
      let raw = "";
      req.on("data", (c) => (raw += c));
      req.on("end", () => {
        let body = {};
        try {
          body = JSON.parse(raw);
        } catch {
          res.writeHead(400);
          return res.end(JSON.stringify({ error: "invalid json" }));
        }
        const events = Array.isArray(body.events) ? body.events : [body];
        const result = processBatch(events);
        res.writeHead(result.rejected ? 207 : 200, {
          "Content-Type": "application/json",
        });
        res.end(JSON.stringify(result));
      });
      return;
    }
    res.writeHead(404);
    res.end();
  });
  server.listen(port, () => console.log(`pitboss-ingest (http) on :${port}`));
}

function main() {
  const args = process.argv.slice(2);
  const batchIdx = args.indexOf("--batch");
  if (batchIdx !== -1) {
    const file = args[batchIdx + 1];
    if (!file) {
      console.error("--batch requires a file path");
      process.exit(1);
    }
    runBatch(file);
  } else {
    runServer();
  }
}

if (require.main === module) {
  main();
}

module.exports = { processBatch };