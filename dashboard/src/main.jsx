import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import App from "./App.jsx";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchInterval: 2500,
      // Live ops dashboard: never show a stale state. Refetch the moment the tab regains
      // focus, keep polling even while backgrounded, and reconnect after a network drop —
      // otherwise a tab left open (e.g. overnight) freezes on its last value.
      refetchOnWindowFocus: true,
      refetchIntervalInBackground: true,
      refetchOnReconnect: true,
      retry: 3,
      staleTime: 1500,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
      <Toaster theme="dark" position="top-right" richColors closeButton />
    </QueryClientProvider>
  </React.StrictMode>
);
