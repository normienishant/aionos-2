/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    // Proxy /api/* to the FastAPI backend so the frontend needs no CORS setup.
    // 127.0.0.1 explicitly: Node may resolve `localhost` to ::1 (IPv6) while
    // uvicorn binds IPv4 only, which makes the rewrite fail with a 500.
    const backend = process.env.BACKEND_URL || "http://127.0.0.1:8000";
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
