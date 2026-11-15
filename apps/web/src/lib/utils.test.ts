import { describe, expect, it } from "vitest";
import { formatBytes, cn } from "./utils";
describe("presentation helpers", () => {
  it("formats sizes without hiding the approval boundary", () => {
    expect(formatBytes(51 * 1024 * 1024)).toBe("51.0 MiB");
    expect(formatBytes(512)).toBe("1 KiB");
  });
  it("merges conflicting Tailwind utilities", () => {
    expect(cn("p-2", false, "p-4")).toBe("p-4");
  });
});
