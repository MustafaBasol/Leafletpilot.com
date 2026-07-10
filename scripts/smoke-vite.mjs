import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { fileURLToPath } from "node:url";

const viteCli = fileURLToPath(new URL("../node_modules/vite/bin/vite.js", import.meta.url));

async function findFreePort() {
  const server = createServer();
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const { port } = server.address();
  await new Promise((resolve, reject) => server.close((error) => (error ? reject(error) : resolve())));
  return port;
}

const port = await findFreePort();
const child = spawn(process.execPath, [viteCli, "--host", "127.0.0.1", "--port", String(port), "--strictPort"], {
  stdio: "ignore",
  shell: false,
});

async function waitForServer(url, attempts = 30) {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) return response;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
  }

  throw new Error(`Timed out waiting for ${url}`);
}

try {
  const response = await waitForServer(`http://127.0.0.1:${port}`);
  const html = await response.text();

  console.log(`Status: ${response.status}`);
  console.log(`Has app root: ${html.includes('id="app"')}`);
  console.log(`Has React entry: ${html.includes('/src/main.jsx')}`);

  process.exitCode = response.ok && html.includes('id="app"') ? 0 : 1;
} finally {
  child.kill();
}
