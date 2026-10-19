import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { PeopleProvider } from "./data/PeopleContext";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <PeopleProvider>
        <App />
      </PeopleProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
