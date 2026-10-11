/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Load the Postgres driver as a normal Node package instead of bundling it
  serverExternalPackages: ["postgres"],
};
export default nextConfig;
