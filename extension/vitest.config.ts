import { defineConfig } from "vitest/config";

export default defineConfig({
  define: {
    __MDTERO_NATIVE_MESSAGING_ENABLED__: false,
  },
  test: {
    environment: "node",
  },
});
