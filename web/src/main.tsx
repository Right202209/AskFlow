import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

function App() {
  return (
    <div>
      <h1>AskFlow</h1>
      <p>Frontend is under construction.</p>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
