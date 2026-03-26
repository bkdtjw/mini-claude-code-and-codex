export default function LoadingDots() {
  return (
    <span className="inline-flex items-center gap-1" aria-label="loading">
      {[0, 1, 2].map((index) => (
        <span
          key={index}
          className="h-1.5 w-1.5 rounded-full bg-current animate-pulse"
          style={{ animationDelay: `${index * 180}ms`, animationDuration: "900ms" }}
        />
      ))}
    </span>
  );
}
