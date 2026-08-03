import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { Absturzanzeige } from "./components/Absturzanzeige";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Absturzanzeige>
      <App />
    </Absturzanzeige>
  </StrictMode>,
);
