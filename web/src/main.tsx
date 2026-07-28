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
import LandingPage from "./pages/LandingPage";
import HomePage from "./pages/HomePage";
import DayPlanPage from "./pages/DayPlanPage";
import WeekPlanPage from "./pages/WeekPlanPage";
import MyRecipesPage from "./pages/MyRecipesPage";
import RecipeSearchPage from "./pages/RecipeSearchPage";
import SharedPlanPage from "./pages/SharedPlanPage";
import EvalsPage from "./pages/EvalsPage";
import { ComingSoonPage } from "./components/ComingSoonPage";

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
            <Route index element={<LandingPage />} />
            <Route path="plan" element={<HomePage />} />
            <Route path="day" element={<DayPlanPage />} />
            <Route path="week" element={<WeekPlanPage />} />
            <Route path="my-recipes" element={<MyRecipesPage />} />
            <Route path="search" element={<RecipeSearchPage />} />
            <Route path="shared/:shareId" element={<SharedPlanPage />} />
            <Route path="evals" element={<EvalsPage />} />
            <Route
              path="chat"
              element={
                <ComingSoonPage
                  title="Chat with Chef — coming soon"
                  message="The tool-calling Chef agent (ROADMAP Phase 3.3) isn't built yet. In the meantime, try the planner for allergy-safe, macro-targeted recommendations."
                />
              }
            />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
