// Reuse the existing Vite installation; no application/configuration file is changed.
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const { createServer } = await import(pathToFileURL(path.join(root, "frontend/node_modules/vite/dist/node/index.js")));
const port = Number(process.env.DEMO_FRONTEND_PORT || 5173);
const backend = process.env.DEMO_BACKEND_URL || "http://127.0.0.1:8000";
if (new URL(backend).hostname !== "127.0.0.1") throw new Error("Recording proxy must stay local");
const server = await createServer({ root: path.join(root, "frontend"), server: {
  host: "127.0.0.1", port, strictPort: true, proxy: { "/api": backend },
} });
await server.listen();
server.printUrls();
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, async () => {
  await server.close(); process.exit(0);
});
