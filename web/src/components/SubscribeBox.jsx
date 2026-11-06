import { useState } from "react";
import { requestSubscription } from "../lib/data";

export default function SubscribeBox({ initialAction = "subscribe", compact = false, banner = false }) {
  const [action, setAction] = useState(initialAction === "unsubscribe" ? "unsubscribe" : "subscribe");
  const [email, setEmail] = useState("");
  const [website, setWebsite] = useState(""); // honeypot
  const [state, setState] = useState({ status: "idle", message: "" });

  async function submit(e) {
    e.preventDefault();
    setState({ status: "sending", message: "" });
    try {
      const res = await requestSubscription({ email, action, website });
      setState({ status: "sent", message: res.message });
    } catch (err) {
      setState({ status: "error", message: err.message });
    }
  }

  return (
    <div className={`subscribe-box${compact ? " compact" : ""}${banner ? " banner" : ""}`}>
      <h3 className="subscribe-title">{action === "subscribe" ? "Get the paper every Monday" : "Unsubscribe"}</h3>
      {!compact && !banner && (
        <p className="subscribe-copy">
          {action === "subscribe"
            ? "One email a week: the three sections, the lead reports and the briefs. Free, and you can leave at any time."
            : "Enter the address you subscribed with. We'll email you a link to confirm."}
        </p>
      )}
      {state.status === "sent" ? (
        <p className="notice notice-ok" role="status">
          {state.message} Click the link in that email to finish.
        </p>
      ) : (
        <form onSubmit={submit} className="subscribe-form">
          <label className="sr-only" htmlFor={`email-${compact}-${banner}`}>
            Email address
          </label>
          <input
            id={`email-${compact}-${banner}`}
            type="email"
            required
            autoComplete="email"
            placeholder="Email address"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <input
            className="hp"
            tabIndex={-1}
            autoComplete="off"
            aria-hidden="true"
            name="website"
            value={website}
            onChange={(e) => setWebsite(e.target.value)}
          />
          <button className="btn btn-ink" type="submit" disabled={state.status === "sending"}>
            {state.status === "sending" ? "Sending…" : action === "subscribe" ? "Subscribe" : "Unsubscribe"}
          </button>
        </form>
      )}
      {state.status === "error" && (
        <p className="notice notice-error" role="alert">
          {state.message}
        </p>
      )}
      <button
        type="button"
        className="link-button"
        onClick={() => {
          setAction(action === "subscribe" ? "unsubscribe" : "subscribe");
          setState({ status: "idle", message: "" });
        }}
      >
        {action === "subscribe" ? "Already subscribed? Unsubscribe" : "Want to subscribe instead?"}
      </button>
    </div>
  );
}
