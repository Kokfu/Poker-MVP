import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

const PUBLIC_ASSETS = [
  "/manifest.webmanifest", "/icons/poker-coach-180.png", "/icons/poker-coach-192.png",
  "/icons/poker-coach-512.png", "/icons/poker-coach-maskable-512.png",
];

/** @returns {import("vite").Plugin} */
export function pokerWebApp() {
  return {
    name: "poker-app-shell",
    apply: "build",
    generateBundle: {
      order: "post",
      handler(_output, bundle) {
        const worker = readFileSync(new URL("./src/service-worker.js", import.meta.url), "utf8");
        const html = bundle["index.html"];
        if (!html || html.type !== "asset") throw new Error("App shell requires the built index.html");

        const hash = createHash("sha256").update(worker).update(html.source);
        const assets = Object.keys(bundle).filter((file) => file.startsWith("assets/") && !file.endsWith(".map")).sort();
        for (const file of assets) hash.update(file);
        for (const file of PUBLIC_ASSETS) hash.update(readFileSync(new URL(`./public${file}`, import.meta.url)));
        this.emitFile({ type: "asset", fileName: "service-worker.js", source: worker
          .replace('"__POKER_SHELL_VERSION__"', JSON.stringify(hash.digest("hex").slice(0, 16)))
          .replace('"__POKER_SHELL_FILES__"', JSON.stringify(["/", ...assets.map((file) => `/${file}`), ...PUBLIC_ASSETS])),
        });
      },
    },
  };
}
