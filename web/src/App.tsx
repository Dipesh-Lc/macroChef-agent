import { Outlet } from "react-router-dom";
import { TopNav } from "./components/TopNav";

export default function App() {
  return (
    <div className="min-h-screen bg-porcelain">
      <TopNav />
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
