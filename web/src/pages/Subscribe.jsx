import { useSearchParams } from "react-router-dom";
import SubscribeBox from "../components/SubscribeBox";
import { useTitle } from "../lib/hooks";

export default function Subscribe() {
  const [params] = useSearchParams();
  const action = params.get("action") === "unsubscribe" ? "unsubscribe" : "subscribe";
  const list = params.get("list");
  const lists = list === "daily" ? ["daily"] : list === "both" ? ["weekly", "daily"] : ["weekly"];
  useTitle(action === "subscribe" ? "Subscribe" : "Unsubscribe");
  return (
    <div className="wrap narrow subscribe-page">
      <SubscribeBox key={`${action}-${list}`} initialAction={action} initialLists={lists} />
      <div className="subscribe-facts">
        <div>
          <strong>Two newsletters.</strong> The weekly edition arrives on Mondays with in-depth reports on three
          sections. The daily brief arrives Monday to Friday with one line on each of the day&rsquo;s relevant papers.
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
