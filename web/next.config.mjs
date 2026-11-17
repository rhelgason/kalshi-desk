/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Load the Postgres driver as a normal Node package instead of bundling it
  serverExternalPackages: ["postgres"],
  // Keep pages the browser just showed for 30 s (11-17), so flipping between time ranges or books and back is
  // instant. A server action that changes a cookie (switching books, opening an office) drops these copies, and
  // the 60 s auto-refresh always asks afresh.
  experimental: { staleTimes: { dynamic: 30 } },
};
export default nextConfig;
