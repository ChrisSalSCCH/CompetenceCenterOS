// Vitest setup — installed at src/test/setup.ts by the Testing integration.
import "@testing-library/jest-dom";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// Unmount React trees rendered during a test so cases stay isolated.
afterEach(() => {
  cleanup();
});
