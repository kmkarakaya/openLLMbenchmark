const http = require("http");

const port = Number(process.env.MOCK_OLLAMA_PORT || 11435);

function sendJson(res, statusCode, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(statusCode, {
    "content-type": "application/json",
    "content-length": Buffer.byteLength(body)
  });
  res.end(body);
}

const server = http.createServer((req, res) => {
  if (!req.url) {
    sendJson(res, 404, { error: "not_found" });
    return;
  }

  if (req.method === "GET" && req.url === "/api/tags") {
    sendJson(res, 200, {
      models: [
        { model: "mock-alpha", name: "mock-alpha" },
        { model: "mock-beta", name: "mock-beta" }
      ]
    });
    return;
  }

  if (req.method === "POST" && req.url === "/api/chat") {
    let raw = "";
    req.on("data", (chunk) => {
      raw += chunk;
    });
    req.on("end", () => {
      let model = "mock-alpha";
      try {
        const payload = JSON.parse(raw || "{}");
        if (payload && typeof payload.model === "string" && payload.model.trim()) {
          model = payload.model.trim();
        }
      } catch {
        // Keep default model on parse failure.
      }

      res.writeHead(200, {
        "content-type": "application/x-ndjson",
        "cache-control": "no-cache",
        connection: "keep-alive"
      });

      const chunks = [
        { message: { role: "assistant", content: `${model} says: ` }, done: false },
        { message: { role: "assistant", content: "streamed response chunk 1. " }, done: false },
        { message: { role: "assistant", content: "streamed response chunk 2." }, done: false },
        { message: { role: "assistant", content: "" }, done: true }
      ];

      let index = 0;
      const timer = setInterval(() => {
        if (index >= chunks.length) {
          clearInterval(timer);
          res.end();
          return;
        }
        res.write(`${JSON.stringify(chunks[index])}\n`);
        index += 1;
      }, 120);
    });
    return;
  }

  sendJson(res, 404, { error: "not_found" });
});

server.listen(port, "127.0.0.1", () => {
  // eslint-disable-next-line no-console
  console.log(`[mock-ollama] listening on 127.0.0.1:${port}`);
});

const shutdown = () => {
  server.close(() => process.exit(0));
};

process.on("SIGTERM", shutdown);
process.on("SIGINT", shutdown);
