import { Outlet } from "react-router-dom";
import { TopNav } from "./components/TopNav";

export default function App() {
  return (
    <div className="min-h-screen bg-porcelain">
      <TopNav />
      {/* `pb-20` reserves space for `TopNav`'s fixed mobile bottom bar
          (ROADMAP Step 4.5, `< 640px`) so it never overlaps page content;
          `sm:pb-6` restores the normal padding once the top nav (not a
          fixed bottom bar) takes over. */}
      <main className="mx-auto max-w-6xl px-4 py-6 pb-20 sm:pb-6">
        <Outlet />
      </main>
    </div>
  );
}
