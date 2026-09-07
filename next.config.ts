import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Enable standalone output for Docker deployment.
  // Produces a self-contained server.js that only needs the
  // .next/standalone, .next/static, and public directories.
  output: "standalone",
};

export default nextConfig;
