import { StrictMode, useSyncExternalStore } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import Broadcast from "./Broadcast";
import { isBroadcastHash } from "./lib/broadcast";
import "./styles.css";

const onHashChange = (notify: () => void) => {
  window.addEventListener("hashchange", notify);
  return () => window.removeEventListener("hashchange", notify);
};

/** The dashboard, or the program output when the hash says so (a hash change switches without a reload). */
function Root() {
  const hash = useSyncExternalStore(onHashChange, () => window.location.hash);
  return isBroadcastHash(hash) ? <Broadcast key={hash} /> : <App />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
