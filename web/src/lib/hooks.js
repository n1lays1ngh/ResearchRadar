import { useEffect, useState } from "react";

/** Run an async loader when deps change: { data, error, loading }. */
export function useAsync(load, deps) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  useEffect(() => {
    let live = true;
    setState((s) => ({ ...s, loading: true, error: null }));
    load()
      .then((data) => live && setState({ data, error: null, loading: false }))
      .catch((error) => live && setState({ data: null, error, loading: false }));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

export function useTitle(title) {
  useEffect(() => {
    document.title = title ? `${title} | The Research Radar` : "The Research Radar";
  }, [title]);
}
