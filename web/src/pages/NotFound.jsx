import { Link } from "react-router-dom";
import { useTitle } from "../lib/hooks";

export default function NotFound() {
  useTitle("Page not found");
  return (
    <div className="wrap narrow empty">
      <div className="kicker">Correction</div>
      <h1 className="page-title">This page doesn&rsquo;t exist</h1>
      <p>
        <Link to="/">Return to the front page →</Link>
      </p>
    </div>
  );
}
