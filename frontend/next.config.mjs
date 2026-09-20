/** @type {import('next').NextConfig} */

// EXPORT=1 -> fully static build (out/) that FastAPI serves itself in the
// single-service Docker deploy. Dev (npm run dev) and the two-service
// deployment (Vercel + Render) keep the /api/* rewrite.
const isStaticExport = process.env.EXPORT === "1";

const nextConfig = {
  ...(isStaticExport ? { output: "export", trailingSlash: true } : {}),
  ...(isStaticExport
    ? {}
    : {
        async rewrites() {
          // Proxy /api/* to the FastAPI backend so the frontend needs no CORS
          // setup. 127.0.0.1 explicitly: Node may resolve `localhost` to ::1
          // (IPv6) while uvicorn binds IPv4 only, which fails with a 500.
          const backend = process.env.BACKEND_URL || "http://127.0.0.1:8000";
          return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
        },
      }),
};

export default nextConfig;
