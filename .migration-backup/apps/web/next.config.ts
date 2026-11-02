import type { NextConfig } from "next";

const apiOrigin = process.env.SWEET_SEATS_API_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Local development proxy. No provider credentials or public environment variables.
  async rewrites() {
    return [{ source: "/api/discovery/:path*", destination: `${apiOrigin}/v1/:path*` }];
  },
};

export default nextConfig;

