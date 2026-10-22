import type { MetadataRoute } from "next";

/** "Add to Home Screen": Kalshi Desk opens full-screen like an app (no Safari bars). */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Kalshi Desk",
    short_name: "Kalshi Desk",
    description: "Your trading employees on Kalshi.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#0f0d1f",
    theme_color: "#0f0d1f",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
