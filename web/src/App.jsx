import { useEffect } from "react";
import { Navigate, Outlet, Route, Routes, useLocation, useSearchParams } from "react-router-dom";
import Footer from "./components/Footer";
import Masthead from "./components/Masthead";
import { loadEditions } from "./lib/data";
import { useAsync } from "./lib/hooks";
import Archive from "./pages/Archive";
import Article from "./pages/Article";
import Brief from "./pages/Brief";
import Browse from "./pages/Browse";
import Confirm from "./pages/Confirm";
import Front from "./pages/Front";
import NotFound from "./pages/NotFound";
import Section from "./pages/Section";
import Subscribe from "./pages/Subscribe";

function Layout() {
  const { data: editions } = useAsync(loadEditions, []);
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return (
    <>
      <a className="skip" href="#main">
        Skip to content
      </a>
      <Masthead latest={editions?.[0]} />
      <main id="main">
        <Outlet />
      </main>
      <Footer />
    </>
  );
}

/** Old email links: /?paper=<id> and /?action=unsubscribe */
function Home() {
  const [params] = useSearchParams();
  if (params.get("paper")) return <Navigate replace to={`/paper/${params.get("paper")}`} />;
  if (params.get("action")) return <Navigate replace to={`/subscribe?action=${params.get("action")}`} />;
  return <Front />;
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="edition/:date" element={<Front />} />
        <Route path="section/:key" element={<Section />} />
        <Route path="brief" element={<Brief />} />
        <Route path="brief/:date" element={<Brief />} />
        <Route path="paper/*" element={<Article />} />
        <Route path="archive" element={<Archive />} />
        <Route path="browse" element={<Browse />} />
        <Route path="subscribe" element={<Subscribe />} />
        <Route path="confirm" element={<Confirm />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
