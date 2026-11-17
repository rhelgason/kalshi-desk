import { cookies } from "next/headers";
import { currentUser } from "./session";
import { MODE_COOKIE, MODE_PREF, THEME_COOKIE, THEME_PREF, parseMode, parseTheme } from "./theme";

/** This device's look and light/dark pick, else the ones saved with their login (app/account.ts savePrefs). */
export async function readLook() {
  const [jar, user] = await Promise.all([cookies(), currentUser()]);
  return {
    theme: parseTheme(jar.get(THEME_COOKIE)?.value ?? (user?.prefs[THEME_PREF] as string)),
    mode: parseMode(jar.get(MODE_COOKIE)?.value ?? (user?.prefs[MODE_PREF] as string)),
  };
}
