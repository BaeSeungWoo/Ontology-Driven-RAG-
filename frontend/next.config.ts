import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  devIndicators: false, // 개발모드에서 뱃지 가시여부 옵션

  reactStrictMode: false, // 개발모드에서 백엔드 호출이 2번씩되는 현상 방지 
  allowedDevOrigins: ['192.168.1.31'],
  async rewrites() {
    const target = process.env.API_PROXY_TARGET || "http://127.0.0.1:8000";
    return ["/api/:path*", "/assets/:path*", "/configs"].map(source => ({
      source, destination: `${target}${source}`,
    }));
  },
};

export default nextConfig;
