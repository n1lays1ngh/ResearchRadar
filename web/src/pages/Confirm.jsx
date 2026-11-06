import { Link, useSearchParams } from "react-router-dom";
import { ErrorNote, Loading } from "../components/Status";
import { confirmSubscription } from "../lib/data";
import { useAsync, useTitle } from "../lib/hooks";

export default function Confirm() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  useTitle("Confirm");
  const { data, error, loading } = useAsync(
    () => (token ? confirmSubscription(token) : Promise.reject(new Error("This link is missing its token."))),
    [token],
  );
  if (loading) return <Loading label="Confirming" />;
  return (
    <div className="wrap narrow confirm">
      {error ? (
        <ErrorNote error={error}>We couldn&rsquo;t confirm that.</ErrorNote>
      ) : (
        <>
          <div className="kicker">{data.action === "subscribe" ? "Welcome aboard" : "Done"}</div>
          <h1 className="page-title">{data.message}</h1>
        </>
      )}
      <p>
        <Link to="/">Read the latest edition →</Link>
      </p>
    </div>
  );
}
