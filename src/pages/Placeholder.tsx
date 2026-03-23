import { useLocation } from "react-router-dom";

export default function Placeholder() {
  const location = useLocation();
  const name = location.pathname.slice(1).replace(/^\w/, (c) => c.toUpperCase());

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-muted-foreground">
      <p className="text-lg font-medium">{name || "Page"}</p>
      <p className="text-sm mt-1">Coming soon in the next stage.</p>
    </div>
  );
}
