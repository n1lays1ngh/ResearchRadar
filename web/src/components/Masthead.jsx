import { Link, NavLink } from "react-router-dom";
import { longDate } from "../lib/format";
import ThemeToggle from "./ThemeToggle";

export default function Masthead({ latest }) {
  const today = longDate(new Date().toISOString());
  return (
    <header className="masthead">
      <div className="utility wrap">
        <span className="utility-date">{today}</span>
        <span className="utility-actions">
          <ThemeToggle />
          {latest?.pdf && (
            <a className="utility-link" href={`/editions/${latest.date}.pdf`} download>
              Today&rsquo;s paper (PDF)
            </a>
          )}
          <Link className="btn btn-ink btn-sm" to="/subscribe">
            Subscribe
          </Link>
        </span>
      </div>
      <div className="wrap nameplate-wrap">
        <Link to="/" className="nameplate" aria-label="The Rinfo, front page">
          The Rinfo
        </Link>
        <p className="motto">Research, in brief · a daily brief and a weekly review of new preprints from arXiv</p>
        <p className="edition-line">
          {latest ? (
            <>
              {latest.edition} <span aria-hidden>·</span> {longDate(latest.date)} <span aria-hidden>·</span>{" "}
              {latest.scanned} preprints read <span aria-hidden>·</span> {latest.picked} selected
            </>
          ) : (
            " "
          )}
        </p>
      </div>
      <nav className="sections-nav" aria-label="Sections">
        <div className="wrap sections-nav-inner">
          <NavLink to="/" end>
            Front Page
          </NavLink>
          {latest?.sections.map((s) => (
            <NavLink key={s.key} to={`/section/${s.key}`}>
              {s.name}
            </NavLink>
          ))}
          <NavLink to="/brief">Daily Brief</NavLink>
          <NavLink to="/browse">Browse arXiv</NavLink>
          <NavLink to="/archive">Archive</NavLink>
        </div>
      </nav>
    </header>
  );
}
