import { describe, expect, it } from "vitest";

import {
  partitionSidebarNav,
  type SidebarNavItem,
  type SidebarPluginManifest,
} from "./sidebar-nav";

const ICON = "icon";

function item(path: string, label: string): SidebarNavItem<string> {
  return { path, label, icon: ICON };
}

function plugin(
  path: string,
  label: string,
  position?: string,
): SidebarPluginManifest {
  return {
    icon: "Radio",
    label,
    tab: { path, ...(position ? { position } : {}) },
  };
}

const CORE = [
  item("/chat", "Chat"),
  item("/sessions", "Sessions"),
  item("/skills", "Skills"),
];

describe("partitionSidebarNav", () => {
  it("pins a plugin after Chat into the core sidebar, not the Plugins section", () => {
    const { coreItems, pluginItems } = partitionSidebarNav(
      CORE,
      [plugin("/listen", "Listen", "after:chat")],
      () => ICON,
    );
    expect(coreItems.map((i) => i.path)).toEqual([
      "/chat",
      "/listen",
      "/sessions",
      "/skills",
    ]);
    expect(coreItems[1]?.label).toBe("Listen");
    expect(pluginItems).toEqual([]);
  });

  it("keeps unpinned plugin tabs in the Plugins section", () => {
    const { coreItems, pluginItems } = partitionSidebarNav(
      CORE,
      [plugin("/achievements", "Achievements", "end")],
      () => ICON,
    );
    expect(coreItems.map((i) => i.path)).toEqual([
      "/chat",
      "/sessions",
      "/skills",
    ]);
    expect(pluginItems.map((i) => i.path)).toEqual(["/achievements"]);
  });

  it("does not pin a tab whose after: target is missing from the built-in list", () => {
    const { coreItems, pluginItems } = partitionSidebarNav(
      CORE,
      [plugin("/achievements", "Achievements", "after:analytics")],
      () => ICON,
    );
    expect(coreItems.map((i) => i.path)).toEqual([
      "/chat",
      "/sessions",
      "/skills",
    ]);
    expect(pluginItems.map((i) => i.path)).toEqual(["/achievements"]);
  });
});
