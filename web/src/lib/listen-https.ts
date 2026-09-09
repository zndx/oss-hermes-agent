/**
 * AgentRTC Listen needs a secure context (getUserMedia). HTTP dashboard
 * navigations to /listen must land on the HTTPS join URL.
 */

export function listenHttpsHref(
  joinUrl: string | undefined,
  location: { origin: string; protocol: string; search: string; hash: string },
): string | null {
  const join = (joinUrl || "").trim();
  if (!join) return null;
  let target: URL;
  try {
    target = new URL(join, location.origin);
  } catch {
    return null;
  }
  if (target.protocol !== "https:") return null;
  if (location.protocol === "https:" && target.origin === location.origin) {
    return null;
  }
  if (location.search && !target.search) target.search = location.search;
  if (location.hash && !target.hash) target.hash = location.hash;
  return target.toString();
}

export function listenNavHref(
  path: string,
  joinUrl: string | undefined,
  location: { origin: string; protocol: string; search: string; hash: string },
): string | undefined {
  if (path !== "/listen") return undefined;
  return listenHttpsHref(joinUrl, location) ?? undefined;
}
