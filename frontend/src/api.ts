/**
 * Resolve an API path relative to the app's base path.
 * In dev (base="/") this is a no-op. Behind a reverse proxy
 * stripping "/bitaxe" (base="/bitaxe/") it prepends the prefix.
 */
const base = import.meta.env.BASE_URL.replace(/\/+$/, ''); // e.g. "" or "/bitaxe"

export function apiUrl(path: string): string {
  return `${base}${path}`;
}

export function wsUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}${base}/ws`;
}
