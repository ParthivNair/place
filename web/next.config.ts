import type { NextConfig } from "next";

/* GITHUB_PAGES=1 builds the static demo for the project Pages site
   (parthivnair.github.io/place): full export, everything under /place,
   trailing slashes so deep links resolve to directory index.html files.
   Dev and the future VPS deployment (docs/04 §9) serve from the domain
   root and take none of this. */
const ghPages = process.env.GITHUB_PAGES === "1";
const basePath = ghPages ? "/place" : "";

const nextConfig: NextConfig = {
  ...(ghPages && { output: "export" as const, basePath, trailingSlash: true }),
  // Client code (sw registration, manifest links) needs the prefix too.
  env: { NEXT_PUBLIC_BASE_PATH: basePath },
};

export default nextConfig;
