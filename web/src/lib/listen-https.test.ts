import { describe, expect, it } from "vitest";

import { listenHttpsHref, listenNavHref } from "./listen-https";

const JOIN = "https://tinybox.dev.vista.zndx.org:9120/listen";

describe("listenHttpsHref", () => {
  it("sends HTTP dashboard Listen to the HTTPS join URL", () => {
    expect(
      listenHttpsHref(JOIN, {
        origin: "http://tinybox.dev.vista.zndx.org:9119",
        protocol: "http:",
        search: "",
        hash: "",
      }),
    ).toBe(JOIN);
  });

  it("keeps agenda query and hash on the HTTPS URL", () => {
    expect(
      listenHttpsHref(JOIN, {
        origin: "http://192.168.1.55:9119",
        protocol: "http:",
        search: "?agenda=note/today",
        hash: "#x",
      }),
    ).toBe(`${JOIN}?agenda=note/today#x`);
  });

  it("does not bounce when already on the HTTPS origin", () => {
    expect(
      listenHttpsHref(JOIN, {
        origin: "https://tinybox.dev.vista.zndx.org:9120",
        protocol: "https:",
        search: "",
        hash: "",
      }),
    ).toBeNull();
  });

  it("ignores a non-https join URL", () => {
    expect(
      listenHttpsHref("http://tinybox:9119/listen", {
        origin: "http://tinybox:9119",
        protocol: "http:",
        search: "",
        hash: "",
      }),
    ).toBeNull();
  });
});

describe("listenNavHref", () => {
  it("only rewrites the Listen item", () => {
    const loc = {
      origin: "http://127.0.0.1:9119",
      protocol: "http:",
      search: "",
      hash: "",
    };
    expect(listenNavHref("/listen", JOIN, loc)).toBe(JOIN);
    expect(listenNavHref("/chat", JOIN, loc)).toBeUndefined();
  });
});
