import { Link, useParams } from "react-router-dom";
import SectionBlock from "../components/SectionBlock";
import { ErrorNote, Loading } from "../components/Status";
import { loadEdition, loadEditions } from "../lib/data";
import { useAsync, useTitle } from "../lib/hooks";

export default function Section() {
  const { key } = useParams();
  const { data, error, loading } = useAsync(async () => {
    const editions = await loadEditions();
    if (!editions.length) return null;
    const edition = await loadEdition(editions[0].date);
    return edition.sections.find((s) => s.key === key) || null;
  }, [key]);
  useTitle(data?.name || key);

  if (loading) return <Loading />;
  if (error) return <ErrorNote error={error}>The section couldn&rsquo;t be loaded.</ErrorNote>;
  if (!data)
    return (
      <div className="wrap empty">
        <h1 className="page-title">No such section this week</h1>
        <p>
          Try <Link to="/browse">browsing arXiv</Link> for <code>{key}</code>.
        </p>
      </div>
    );
  return (
    <div className="wrap">
      <SectionBlock section={data} showOverview headingLink={false} />
      <p className="section-more">
        Want more from {data.key}? <Link to={`/browse?category=${data.key}`}>See the newest preprints on arXiv →</Link>
      </p>
    </div>
  );
}
