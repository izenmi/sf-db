import { Link } from "react-router-dom";
import type { SeriesGenerated, WorkGenerated } from "../../types";
import { WorkCover } from "../common/WorkCover";
import { colorForYear } from "../common/yearColor";

const COVER_COUNT = 4;
const THEME_COUNT = 4;
const AUTHOR_COUNT = 2;

/** シリーズ一覧のカード。名前と件数だけの行だと、シリーズが何の話なのか一覧から分からない。
 *  トップの「ピックアップ作品」と同じ密度になるよう、書影・刊行年・著者・テーマまで出す。
 *
 *  表示する値はすべて渡された作品(刊行年の古い順)から導出していて、
 *  シリーズ側に持たせた項目はない。作品を足せば書影も年も自動で更新される。 */
export function SeriesCard({ series, works }: { series: SeriesGenerated; works: WorkGenerated[] }) {
  const years = works.map((w) => w.firstPublishedYear);
  const from = Math.min(...years);
  const to = Math.max(...years);

  const authors = [...new Set(works.flatMap((w) => w.authorNames))];
  // ネタバレテーマは WorkCard と同じ理由で伏せる(一覧を眺めるだけで割れてしまうため)
  const themeCounts = new Map<string, { name: string; n: number }>();
  for (const w of works) {
    const hidden = new Set(w.spoilerThemeIds);
    w.themeIds.forEach((id, i) => {
      if (hidden.has(id)) return;
      const e = themeCounts.get(id) ?? { name: w.themeNames[i] ?? id, n: 0 };
      e.n += 1;
      themeCounts.set(id, e);
    });
  }
  const themes = [...themeCounts.entries()]
    .sort((a, b) => b[1].n - a[1].n || a[1].name.localeCompare(b[1].name, "ja"))
    .slice(0, THEME_COUNT);

  const href = `/series/${encodeURIComponent(series.id)}`;

  return (
    <div className="series-card">
      <Link to={href} className="work-card__cover-link" aria-label={series.name} />
      <div className="series-card__covers">
        {works.slice(0, COVER_COUNT).map((w) => (
          <WorkCover title={w.title} coverUrl={w.coverUrl} size="sm" key={w.id} />
        ))}
      </div>
      <div className="series-card__content">
        <div className="series-card__title">
          {series.name}
          <span className="entity-list__count">{series.workCount}作</span>
        </div>
        <div className="work-card__meta">
          <span className={`winner-year winner-year--${colorForYear(from)}`}>
            {from === to ? `${from}` : `${from}–${to}`}
          </span>{" "}
          {authors.slice(0, AUTHOR_COUNT).join("・")}
          {authors.length > AUTHOR_COUNT && ` ほか${authors.length - AUTHOR_COUNT}名`}
        </div>
        {themes.length > 0 && (
          <div className="chip-row">
            {themes.map(([id, t]) => (
              <Link className="chip" to={`/themes/${id}`} key={id}>
                {t.name}
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
