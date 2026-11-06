import { useSearchParams } from "react-router-dom";
import SubscribeBox from "../components/SubscribeBox";
import { useTitle } from "../lib/hooks";

export default function Subscribe() {
  const [params] = useSearchParams();
  const action = params.get("action") === "unsubscribe" ? "unsubscribe" : "subscribe";
  useTitle(action === "subscribe" ? "Subscribe" : "Unsubscribe");
  return (
    <div className="wrap narrow subscribe-page">
      <SubscribeBox key={action} initialAction={action} />
      <div className="subscribe-facts">
        <div>
          <strong>Every Monday, 8:00 IST.</strong> Three sections built on official arXiv categories, each with a lead
          report, two further reports and the week&rsquo;s briefs.
        </div>
        <div>
          <strong>Your address stays private.</strong> It is stored encrypted, used only to send the newsletter, and never
          shown to other readers.
        </div>
        <div>
          <strong>Confirmed by email.</strong> Nobody can subscribe or unsubscribe you without clicking the link we send.
        </div>
      </div>
    </div>
  );
}
