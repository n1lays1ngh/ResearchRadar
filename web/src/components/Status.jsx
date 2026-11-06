export function Loading({ label = "Loading" }) {
  return (
    <div className="status" role="status">
      <span className="status-dots">{label}</span>
    </div>
  );
}

export function ErrorNote({ error, children }) {
  return (
    <div className="status status-error" role="alert">
      <p>{children || "Something went wrong."}</p>
      {error && <p className="status-detail">{String(error.message || error)}</p>}
    </div>
  );
}
