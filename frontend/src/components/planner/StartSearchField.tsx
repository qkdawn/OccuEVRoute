import { useEffect, useMemo, useState } from "react";
import { searchLocations } from "../../api";
import type { Point } from "../../types";
import { coordinateSearchResult, type StartSearchResult, startSearchResult } from "./startSearch";

interface StartSearchFieldProps {
  onSelect: (point: Point) => void;
}

export function StartSearchField({ onSelect }: StartSearchFieldProps) {
  const [query, setQuery] = useState("");
  const [remoteResults, setRemoteResults] = useState<StartSearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const coordinateResult = useMemo(() => coordinateSearchResult(query), [query]);
  const trimmedQuery = query.trim();
  const results = coordinateResult ? [coordinateResult] : remoteResults;

  useEffect(() => {
    if (!trimmedQuery || coordinateResult) {
      setRemoteResults([]);
      setSearchError(null);
      setIsSearching(false);
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setIsSearching(true);
      setSearchError(null);
      searchLocations(trimmedQuery)
        .then((locations) => {
          if (!controller.signal.aborted) setRemoteResults(locations.map(startSearchResult));
        })
        .catch(() => {
          if (!controller.signal.aborted) {
            setRemoteResults([]);
            setSearchError("Search unavailable");
          }
        })
        .finally(() => {
          if (!controller.signal.aborted) setIsSearching(false);
        });
    }, 260);

    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [coordinateResult, trimmedQuery]);

  return (
    <div className="start-search">
      <input
        type="search"
        value={query}
        placeholder="Search real place or paste coordinates"
        aria-label="Search start location"
        onChange={(event) => setQuery(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && results[0]) {
            onSelect(results[0].point);
            setQuery(results[0].label);
          }
        }}
      />
      {isSearching && <span className="start-search-status">Searching...</span>}
      {searchError && <span className="start-search-status">{searchError}</span>}
      {results.length > 0 && (
        <div className="start-search-results">
          {results.map((result) => (
            <button
              type="button"
              key={result.id}
              onClick={() => {
                onSelect(result.point);
                setQuery(result.label);
              }}
            >
              <span>{result.label}</span>
              <small>
                {result.point.lat.toFixed(5)}, {result.point.lng.toFixed(5)}
              </small>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
