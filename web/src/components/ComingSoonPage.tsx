export function ComingSoonPage({ title, message }: { title: string; message: string }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-sage-line bg-white px-6 py-16 text-center">
      <h1 className="font-display text-xl font-semibold text-cast-iron">{title}</h1>
      <p className="max-w-md text-sm text-cast-iron/70">{message}</p>
    </div>
  );
}
