import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { registerSW } from "virtual:pwa-register";
import App from "./App";
import { Absturzanzeige } from "./components/Absturzanzeige";
import "./index.css";

// Eine neue Fassung muss von allein ankommen — Vincenz wird keine
// Hinweismeldung wegtippen. Der Service Worker aktualisiert sich beim
// Start; zusätzlich fragen wir beim Zurückholen der App nach, weil eine
// installierte PWA auf dem Handy tage- oder wochenlang nicht neu lädt.
let registrierung: ServiceWorkerRegistration | undefined;
registerSW({
  immediate: true,
  onRegisteredSW(_url, r) {
    registrierung = r;
  },
});
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") {
    void registrierung?.update();
  }
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Absturzanzeige>
      <App />
    </Absturzanzeige>
  </StrictMode>,
);
