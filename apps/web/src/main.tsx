import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "@/assets/styles.css";
import "@/assets/interface.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode><App /></StrictMode>,
);
