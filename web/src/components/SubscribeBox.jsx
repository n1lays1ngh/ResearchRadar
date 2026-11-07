import { useState } from "react";
import { requestSubscription } from "../lib/data";

const OPTIONS = [
  { key: "weekly", label: "The weekly edition", note: "Sundays: in-depth reports" },
  { key: "daily", label: "The daily brief", note: "Monday to Friday, plus a Saturday week in review" },
];

export default function SubscribeBox({
  initialAction = "subscribe",
  initialLists = ["weekly"],
  compact = false,
  banner = false,
}) {
  const [action, setAction] = useState(initialAction === "unsubscribe" ? "unsubscribe" : "subscribe");
  const [lists, setLists] = useState(initialLists);
  const [email, setEmail] = useState("");
  const [website, setWebsite] = useState(""); // honeypot
  const [state, setState] = useState({ status: "idle", message: "" });
  const id = `email-${compact}-${banner}`;

  const toggle = (key) =>
    setLists((cur) => (cur.includes(key) ? cur.filter((k) => k !== key) : [...cur, key]));

  async function submit(e) {
    e.preventDefault();
    if (action === "subscribe" && lists.length === 0) {
      setState({ status: "error", message: "Choose at least one newsletter." });
      return;
    }
    setState({ status: "sending", message: "" });
    try {
      const res = await requestSubscription({ email, action, lists, website });
      setState({ status: "sent", message: res.message });
    } catch (err) {
      setState({ status: "error", message: err.message });
    }
  }

  const title =
    action === "unsubscribe" ? "Unsubscribe" : compact || banner ? "Get The Rinfo by email" : "Subscribe";

  return (
    <div className={`subscribe-box${compact ? " compact" : ""}${banner ? " banner" : ""}`}>
      <h3 className="subscribe-title">{title}</h3>
      {!compact && !banner && (
        <p className="subscribe-copy">
          {action === "subscribe"
            ? "Free. Choose what you'd like to receive; you can change it or leave at any time. Already subscribed? Subscribe again with a different choice to update it."
            : "Enter the address you subscribed with. We'll email you a link to confirm."}
        </p>
      )}
      {state.status === "sent" ? (
        <p className="notice notice-ok" role="status">
          {state.message} Click the link in that email to finish.
        </p>
      ) : (
        <form onSubmit={submit}>
          {action === "subscribe" && (
            <fieldset className="lists">
              <legend className="sr-only">Newsletters</legend>
              {OPTIONS.map((o) => (
                <label key={o.key} className={lists.includes(o.key) ? "list-option on" : "list-option"}>
                  <input type="checkbox" checked={lists.includes(o.key)} onChange={() => toggle(o.key)} />
                  <span>
                    <strong>{o.label}</strong>
                    <small>{o.note}</small>
                  </span>
                </label>
              ))}
            </fieldset>
          )}
          <div className="subscribe-form">
            <label className="sr-only" htmlFor={id}>
              Email address
            </label>
            <input
              id={id}
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
          </div>
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
