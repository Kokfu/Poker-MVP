import "./pwa.css";

if (import.meta.env.PROD && window.isSecureContext && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    void navigator.serviceWorker.register("/service-worker.js").catch((error) => {
      console.warn("Poker Coach could not prepare the offline shell", error);
    });
  }, { once: true });
}
