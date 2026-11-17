import { cookies } from "next/headers";
import { currentUser } from "./session";
import { MODE_COOKIE, MODE_PREF, THEME_COOKIE, THEME_PREF, parseMode, parseTheme } from "./theme";

/**
 * Someone signed in: the theme saved with their login (app/account.ts savePrefs), so a change on one device follows
 * them to every other (11-17: the device's own cookie used to win). Otherwise (the manager by password, or nobody
 * signed in yet) this device's pick.
 */
export async function readLook() {
  const [jar, user] = await Promise.all([cookies(), currentUser()]);
  return {
    theme: parseTheme((user?.prefs[THEME_PREF] as string) ?? jar.get(THEME_COOKIE)?.value),
    mode: parseMode((user?.prefs[MODE_PREF] as string) ?? jar.get(MODE_COOKIE)?.value),
  };
}
