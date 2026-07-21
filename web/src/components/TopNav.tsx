import { NavLink } from "react-router-dom";

const ROUTES: { to: string; label: string }[] = [
  { to: "/", label: "Planner" },
  { to: "/day", label: "Day" },
  { to: "/week", label: "Week" },
  { to: "/batch", label: "Batch" },
  { to: "/my-recipes", label: "My recipes" },
];

function navLinkClassName({ isActive }: { isActive: boolean }): string {
  return [
    "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
    isActive ? "bg-cast-iron text-porcelain" : "text-cast-iron/80 hover:bg-sage-line/60",
  ].join(" ");
}

export function TopNav() {
  return (
    <header className="border-b border-sage-line bg-white">
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
  );
}
