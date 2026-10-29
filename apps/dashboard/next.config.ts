import type { NextConfig } from "next";
const config: NextConfig = {
  output: "export",
  experimental: { cpus: 2 },
  basePath: "/workbench",
  trailingSlash: true,
  images: { unoptimized: true },
  poweredByHeader: false,
};
export default config;
