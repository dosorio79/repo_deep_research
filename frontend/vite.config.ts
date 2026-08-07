import tailwindcss from "@tailwindcss/vite";
import { tanstackStart } from "@tanstack/react-start/plugin/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiProxyTarget = env["VITE_API_PROXY_TARGET"] || "http://127.0.0.1:8000";
  const apiProxy = {
    target: apiProxyTarget,
    changeOrigin: true,
    rewrite: (path: string) => path.replace(/^\/api/, ""),
  };

  return {
    plugins: [
      tailwindcss(),
      tanstackStart({
        server: { entry: "server" },
        importProtection: {
          behavior: "error",
          client: {
            files: ["**/server/**"],
            specifiers: ["server-only"],
          },
        },
      }),
      react(),
    ],
    server: {
      proxy: {
        "/api": apiProxy,
      },
    },
    preview: {
      proxy: {
        "/api": apiProxy,
      },
    },
    resolve: {
      alias: {
        "@": `${import.meta.dirname}/src`,
      },
      tsconfigPaths: true,
    },
  };
});
