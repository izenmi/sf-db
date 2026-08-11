import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./theme/theme.css";
import "./ui/common/common.css";

// Backward-compat: this app used HashRouter (URLs like #/works/xxx) before switching to
// BrowserRouter for SEO. Rewrite any bookmarked/shared hash URL to its clean-path equivalent
// before the router mounts, so old links keep working instead of silently landing on the home page.
if (location.hash.startsWith("#/")) {
  const base = import.meta.env.BASE_URL.replace(/\/$/, "");
  history.replaceState(null, "", base + location.hash.slice(1));
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
