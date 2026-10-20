/** `localStorage` when the browser allows it (private mode and sandboxes may throw), else null. */
export function localStorageOrNull(): Storage | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}
