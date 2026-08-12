import { useParams } from "react-router-dom";
import { getSeries } from "../../data/manifest";
import { useAsyncData } from "../common/useAsyncData";
import { Loading, ErrorState, EmptyState } from "../common/Status";
import { useWorkFilter } from "../common/useWorkFilter";
import { BASE_PATH, SITE_NAME, breadcrumbJsonLd, useSeo } from "../common/useSeo";
import { WorkGrid } from "../common/WorkGrid";
import { colorForYear } from "../common/yearColor";

/** シリーズ詳細。並び順の既定だけ他の一覧と変えて**刊行年の古い順**にしている。
 *  シリーズは第1作から読むものなので、新しい順に並べると使い物にならない。 */
export function SeriesDetailPage() {
  const { id } = useParams<{ id: string }>();
  const name = id ? decodeURIComponent(id) : "";
  const state = useAsyncData(() => getSeries(name), [name]);
  const series = state.status === "ready" ? state.data : undefined;
  const { sorted, controls, coverView } = useWorkFilter(series?.works, "year-asc");

  useSeo({
    title: series?.name,
    description: series
      ? `〈${series.name}〉シリーズのSF小説${series.workCount}作品を刊行順に一覧。あらすじ・著者・出版社・受賞歴つき。`
      : undefined,
    jsonLd: series
      ? breadcrumbJsonLd([
          { name: SITE_NAME, path: BASE_PATH },
          { name: "シリーズ一覧", path: `${BASE_PATH}series` },
          { name: series.name, path: `${BASE_PATH}series/${encodeURIComponent(series.id)}` },
        ])
      : undefined,
  });

  return (
    <div className="page">
      {state.status === "loading" && <Loading />}
      {state.status === "error" && <ErrorState error={state.error} />}
      {state.status === "ready" && !series && <EmptyState text="見つかりませんでした。" />}
      {state.status === "ready" && series && (
        <>
          <h1>{series.name}</h1>
          <p className="page-subtitle">
            {(() => {
              const years = series.works.map((w) => w.firstPublishedYear);
              const from = Math.min(...years);
              const to = Math.max(...years);
              const authors = [...new Set(series.works.flatMap((w) => w.authorNames))];
              return (
                <>
                  <span className={`winner-year winner-year--${colorForYear(from)}`}>
                    {from === to ? `${from}` : `${from}–${to}`}
                  </span>{" "}
                  {series.workCount}作品（刊行順） / {authors.join("・")}
                </>
              );
            })()}
          </p>
          {controls}
          {sorted.length === 0 && <EmptyState />}
          <WorkGrid works={sorted} coverView={coverView} />
        </>
      )}
    </div>
  );
}
