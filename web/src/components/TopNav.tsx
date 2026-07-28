import { NavLink } from "react-router-dom";

const ROUTES: { to: string; label: string }[] = [
  { to: "/", label: "Planner" },
  { to: "/day", label: "Day" },
  { to: "/week", label: "Week" },
  { to: "/search", label: "Search" },
  { to: "/my-recipes", label: "My recipes" },
];

function navLinkClassName({ isActive }: { isActive: boolean }): string {
  return [
    "rounded-md px-3 py-1.5 text-sm font-medium transition-colors duration-200 ease-out",
    isActive ? "bg-cast-iron text-porcelain" : "text-cast-iron/80 hover:bg-sage-line/60",
  ].join(" ");
}

// Bottom-bar variant (ROADMAP Step 4.5: "nav becomes a bottom bar under
// 640px") -- same active/inactive states as the top nav's pill styling,
// but stacked as an even-width row of tap targets instead of a wrapping
// inline list, which reads better as a fixed bottom bar on a narrow
// viewport.
function bottomNavLinkClassName({ isActive }: { isActive: boolean }): string {
  return [
    "flex flex-1 items-center justify-center px-2 py-2.5 text-xs font-medium transition-colors duration-200 ease-out",
    isActive ? "text-basil" : "text-cast-iron/70",
  ].join(" ");
}

export function TopNav() {
  return (
    <>
      {/* Desktop/tablet top nav -- hidden below the `sm` breakpoint (640px),
          where the bottom bar below takes over (ROADMAP Step 4.5). */}
      <header className="hidden border-b border-sage-line bg-white sm:block">
        <div className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
          <span className="font-display text-lg font-semibold tracking-tight text-cast-iron">
            MacroChef
          </span>
          <nav className="flex flex-wrap gap-1">
            {ROUTES.map((route) => (
              <NavLink key={route.to} to={route.to} end={route.to === "/"} className={navLinkClassName}>
                {route.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      {/* Mobile brand bar -- the bottom bar below carries navigation, so
          this keeps the "MacroChef" identity visible without duplicating
          nav links at the top of a narrow viewport. */}
      <header className="border-b border-sage-line bg-white px-4 py-3 sm:hidden">
        <span className="font-display text-lg font-semibold tracking-tight text-cast-iron">MacroChef</span>
      </header>

      {/* Mobile bottom nav bar, `< 640px` only (ROADMAP Step 4.5). Fixed to
          the viewport bottom -- `App.tsx` reserves matching bottom padding
          on `main` so page content is never hidden behind it. */}
      <nav
        aria-label="Primary"
        className="fixed inset-x-0 bottom-0 z-40 flex border-t border-sage-line bg-white sm:hidden"
      >
        {ROUTES.map((route) => (
          <NavLink key={route.to} to={route.to} end={route.to === "/"} className={bottomNavLinkClassName}>
            {route.label}
          </NavLink>
        ))}
      </nav>
    </>
  );
}
