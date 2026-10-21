export default function QueryState({
  loading,
  error,
}: {
  loading: boolean;
  error: unknown;
}) {
  if (loading) {
    return <div className="directory-empty" role="status"><strong>Loading facility data…</strong></div>;
  }
  if (error) {
    const message = error instanceof Error ? error.message : "Unable to load facility data.";
    return <div className="directory-empty" role="alert"><strong>Facility data unavailable</strong><p>{message}</p></div>;
  }
  return null;
}
