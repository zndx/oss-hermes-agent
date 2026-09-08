/**
 * Dashboard left-nav merge: built-in items plus plugin tabs.
 *
 * Plugin manifests may pin themselves next to a built-in with
 * `tab.position: "after:chat"` / `"before:sessions"`. Those pins stay in the
 * core sidebar instead of dropping into the Plugins section, so surfaces like
 * AgentRTC Listen sit next to Chat rather than below the fold.
 */

export type SidebarNavItem<TIcon> = {
  icon: TIcon;
  label: string;
  labelKey?: string;
  path: string;
};

export type SidebarPluginManifest = {
  icon: string;
  label: string;
  tab: {
    hidden?: boolean;
    override?: string;
    path: string;
    position?: string;
  };
};

function positionTarget(pos: string, prefix: "after:" | "before:"): string {
  return "/" + pos.slice(prefix.length);
}

export function buildNavItems<TIcon>(
  builtIn: SidebarNavItem<TIcon>[],
  manifests: SidebarPluginManifest[],
  resolveIcon: (name: string) => TIcon,
): SidebarNavItem<TIcon>[] {
  const items = [...builtIn];

  for (const manifest of manifests) {
    if (manifest.tab.override) continue;
    if (manifest.tab.hidden) continue;

    const pluginItem: SidebarNavItem<TIcon> = {
      path: manifest.tab.path,
      label: manifest.label,
      icon: resolveIcon(manifest.icon),
    };

    const pos = manifest.tab.position ?? "end";
    if (pos === "end") {
      items.push(pluginItem);
    } else if (pos.startsWith("after:")) {
      const target = positionTarget(pos, "after:");
      const idx = items.findIndex((i) => i.path === target);
      items.splice(idx >= 0 ? idx + 1 : items.length, 0, pluginItem);
    } else if (pos.startsWith("before:")) {
      const target = positionTarget(pos, "before:");
      const idx = items.findIndex((i) => i.path === target);
      items.splice(idx >= 0 ? idx : items.length, 0, pluginItem);
    } else {
      items.push(pluginItem);
    }
  }

  return items;
}

/** Split merged nav into built-in sidebar entries vs plugin tabs, preserving plugin order hints. */
export function partitionSidebarNav<TIcon>(
  builtIn: SidebarNavItem<TIcon>[],
  manifests: SidebarPluginManifest[],
  resolveIcon: (name: string) => TIcon,
): { coreItems: SidebarNavItem<TIcon>[]; pluginItems: SidebarNavItem<TIcon>[] } {
  const merged = buildNavItems(builtIn, manifests, resolveIcon);
  const builtinPaths = new Set(builtIn.map((i) => i.path));
  const corePinned = new Set<string>();
  for (const manifest of manifests) {
    const pos = manifest.tab.position ?? "end";
    const colon = pos.indexOf(":");
    if (colon < 0) continue;
    const target = "/" + pos.slice(colon + 1);
    if (builtinPaths.has(target)) corePinned.add(manifest.tab.path);
  }
  const coreItems: SidebarNavItem<TIcon>[] = [];
  const pluginItems: SidebarNavItem<TIcon>[] = [];
  for (const item of merged) {
    if (builtinPaths.has(item.path) || corePinned.has(item.path)) coreItems.push(item);
    else pluginItems.push(item);
  }
  return { coreItems, pluginItems };
}
