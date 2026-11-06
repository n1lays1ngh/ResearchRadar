import { Link } from "react-router-dom";

export default function Footer() {
  return (
    <footer className="site-footer">
      <div className="wrap">
        <div className="footer-plate">The Rinfo</div>
        <nav className="footer-links" aria-label="Footer">
          <Link to="/">Front Page</Link>
          <Link to="/brief">Daily Brief</Link>
          <Link to="/archive">Archive</Link>
          <Link to="/browse">Browse arXiv</Link>
          <Link to="/subscribe">Subscribe</Link>
          <Link to="/subscribe?action=unsubscribe">Unsubscribe</Link>
        </nav>
        {/* <p className="footer-note">
          Compiled automatically each Monday from the arXiv preprint server. Reports are written by a language model
          from each paper&rsquo;s own text and have not been reviewed by a human editor; they may contain errors.
          Preprints are not peer-reviewed. Consult the original paper before citing any claim.
        </p> */}
      </div>
    </footer>
  );
}
