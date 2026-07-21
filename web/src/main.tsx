import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import "@fontsource/bricolage-grotesque/500.css";
import "@fontsource/bricolage-grotesque/600.css";
import "@fontsource/bricolage-grotesque/700.css";
import "@fontsource-variable/instrument-sans";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";
import "./index.css";

import App from "./App";
import HomePage from "./pages/HomePage";
import DayPlanPage from "./pages/DayPlanPage";
import WeekPage from "./pages/WeekPage";
import BatchPage from "./pages/BatchPage";
import MyRecipesPage from "./pages/MyRecipesPage";
import SharedPlanPage from "./pages/SharedPlanPage";

const queryClient = new QueryClient();

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Missing #root element in index.html");
}

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<App />}>
            <Route index element={<HomePage />} />
            <Route path="day" element={<DayPlanPage />} />
            <Route path="week" element={<WeekPage />} />
            <Route path="batch" element={<BatchPage />} />
            <Route path="my-recipes" element={<MyRecipesPage />} />
            <Route path="shared/:shareId" element={<SharedPlanPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
