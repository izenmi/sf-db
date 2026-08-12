import { useState } from "react";
import { getSeriesList } from "../../data/manifest";
import { useAsyncData } from "../common/useAsyncData";
import { Loading, ErrorState, EmptyState } from "../common/Status";
import { useSeo } from "../common/useSeo";
import { SeriesCard } from "./SeriesCard";

/** シリーズは works.json の seriesName から build 時に組み立てている(SeriesGenerated 参照)。
 *  1作しかないシリーズもページ自体は存在するが、一覧の既定表示からは畳んでおく。
 *  続刊がまだ登録されていないだけのものが大半で、そのまま並べると一覧が薄まるため。 */
export function SeriesListPage() {
  const state = useAsyncData(getSeriesList, []);
  const [showSingles, setShowSingles] = useState(false);
  const [q, setQ] = useState("");

  useSeo({
    title: "シリーズ一覧",
    description:
      state.status === "ready"
        ? `〈ハイペリオン四部作〉〈機龍警察〉〈クラッシャージョウ〉など${state.data.length}件のシリーズと、刊行順の作品一覧。`
        : undefined,
  });

  const all = state.status === "ready" ? state.data : [];
  const keyword = q.trim().toLowerCase();
  const matched = keyword ? all.filter((s) => s.name.toLowerCase().includes(keyword)) : all;
  const multi = matched.filter((s) => s.workCount > 1);
  const singles = matched.filter((s) => s.workCount === 1);

  return (
    <div className="page">
      <h1>シリーズ</h1>
      {state.status === "loading" && <Loading />}
      {state.status === "error" && <ErrorState error={state.error} />}
      {state.status === "ready" && (
        <>
          <p className="page-subtitle">
            {multi.length}件（2作以上）
            {singles.length > 0 && ` / 1作のみ ${singles.length}件`}
          </p>
          <div className="filter-row">
            <input
              type="search"
              value={q}
              placeholder="シリーズ名で絞り込み"
              aria-label="シリーズ名で絞り込み"
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          {multi.length === 0 && singles.length === 0 && <EmptyState />}
          <div className="series-grid">
            {multi.map((s) => (
              <SeriesCard series={s} key={s.id} />
            ))}
          </div>
          {singles.length > 0 && (
            <>
              <button
                type="button"
                className="filter-clear-btn"
                aria-expanded={showSingles}
                onClick={() => setShowSingles((v) => !v)}
              >
                {showSingles ? "1作のみのシリーズを隠す" : `1作のみのシリーズも表示（${singles.length}件）`}
              </button>
              {showSingles && (
                <div className="series-grid">
                  {singles.map((s) => (
                    <SeriesCard series={s} key={s.id} />
                  ))}
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
