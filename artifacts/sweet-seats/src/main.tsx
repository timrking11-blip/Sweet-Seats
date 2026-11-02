import { createRoot } from "react-dom/client";

import App from "./App";
import { applyBrandFoundation } from "../../../lib/sweet-seats-brand/foundation";
import "../../../lib/sweet-seats-brand/tokens.css";
import "../../../lib/sweet-seats-brand/controls.css";
import "./app/globals.css";

applyBrandFoundation(document.documentElement);
createRoot(document.getElementById("root")!).render(<App />);
