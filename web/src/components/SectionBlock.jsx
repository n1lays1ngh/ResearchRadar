import { Link } from "react-router-dom";
import { Briefs, Elsewhere, Kicker, Story } from "./Story";

/** One section of an edition. skipLead: the front page already shows the lead at the top. */
export default function SectionBlock({ section, skipLead = false, showOverview = false, headingLink = true }) {
  const [lead, ...reports] = section.featured;
  const rest = skipLead ? reports : section.featured;
  return (
    <section className="section-block" id={section.key}>
      <header className="section-head">
        <h2 className="section-name">
          {headingLink ? <Link to={`/section/${section.key}`}>{section.name}</Link> : section.name}
        </h2>
        <span className="section-code">arXiv {section.key}</span>
      </header>
      <p className="section-focus">Coverage: {section.focus}.</p>
      {showOverview && section.overview && (
        <div className="overview">
          <Kicker>The week in brief</Kicker>
          <p>{section.overview}</p>
        </div>
      )}
      <div className={skipLead ? "section-grid section-grid-even" : "section-grid"}>
        {!skipLead && lead && (
          <div className="section-lead">
            <Story paper={lead} size="lead" kicker="Lead story" />
          </div>
        )}
        <div className={skipLead ? "section-reports section-reports-row" : "section-reports"}>
          {(skipLead ? rest : reports).map((p) => (
            <Story key={p.id} paper={p} size="standard" kicker="Report" />
          ))}
          {skipLead && <Briefs papers={section.more} title={`In brief from ${section.key}`} />}
        </div>
      </div>
      {!skipLead && <Briefs papers={section.more} title={`In brief from ${section.key}`} />}
      <Elsewhere items={section.beyond} />
    </section>
  );
}
