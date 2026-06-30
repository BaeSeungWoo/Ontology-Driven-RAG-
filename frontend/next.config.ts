import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  devIndicators: false, // 개발모드에서 뱃지 가시여부 옵션

  reactStrictMode: false, // 개발모드에서 백엔드 호출이 2번씩되는 현상 방지 
};

module.exports = {
  allowedDevOrigins: ['192.168.1.31'],
}

export default nextConfig;
