import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getWork, getWorks } from "../../data/manifest";
import { useAsyncData } from "../common/useAsyncData";
import { Loading, ErrorState, EmptyState } from "../common/Status";
import { WorkCard } from "../common/WorkCard";
import { WorkCover, amazonSearchUrl, rakutenBooksUrl } from "../common/WorkCover";
import { BASE_PATH, DEFAULT_OG_IMAGE, SITE_NAME, breadcrumbJsonLd, useSeo } from "../common/useSeo";
import type { WorkGenerated } from "../../types";

const STATUS_LABEL: Record<string, string> = {
  completed: "完結",
  ongoing: "刊行中",
  unknown: "不明",
};

function workJsonLd(id: string, w: WorkGenerated) {
  return [
    {
      "@context": "https://schema.org",
      "@type": "Book",
      name: w.title,
      inLanguage: "ja",
      author: w.authorNames.map((name) => ({ "@type": "Person", name })),
      ...(w.translatorNames.length > 0 && {
        translator: w.translatorNames.map((name) => ({ "@type": "Person", name })),
      }),
      publisher: { "@type": "Organization", name: w.publisherName },
      datePublished: String(w.firstPublishedYear),
      // Spoiler tags are left out of the structured data too — search snippets are exactly the
      // place a reader would meet them without having chosen to.
      genre: w.themeIds.filter((tid) => !w.spoilerThemeIds.includes(tid)).map((tid) => w.themeNames[w.themeIds.indexOf(tid)]),
      description: w.synopsis,
      ...(w.coverUrl && { image: w.coverUrl }),
      ...(w.awardSummaries.length > 0 && {
        award: w.awardSummaries.map((a) => `${a.awardName} ${a.result}(${a.year})`),
      }),
    },
    breadcrumbJsonLd([
      { name: SITE_NAME, path: BASE_PATH },
      { name: "作品一覧", path: `${BASE_PATH}works` },
      { name: w.title, path: `${BASE_PATH}works/${id}` },
    ]),
  ];
}

export function WorkDetailPage() {
  const { id } = useParams<{ id: string }>();
  const state = useAsyncData(() => getWork(id!), [id]);
  const work = state.status === "ready" ? state.data : undefined;
  // Deliberately component-local and not persisted: every visit to a work page starts with the
  // spoiler tags hidden, even if the reader revealed them on a different work a moment ago.
  const [spoilersShown, setSpoilersShown] = useState(false);

  // getWorks() resolves from the same cached works.json that getWork() above already pulled,
  // so this costs no extra request.
  const allWorksState = useAsyncData(getWorks, []);
  const relatedWorks = useMemo(() => {
    if (allWorksState.status !== "ready" || !work?.relatedWorkIds) return [];
    const byId = new Map(allWorksState.data.map((x) => [x.id, x]));
    return work.relatedWorkIds
      .map((relatedId) => byId.get(relatedId))
      .filter((x): x is WorkGenerated => Boolean(x));
  }, [allWorksState, work]);

  useSeo({
    title: work?.title,
    description: work
      ? `${work.title}(${work.authorNames.join("・")}/${work.publisherName})のあらすじ・刊行年・受賞歴・テーマをまとめて紹介。${work.synopsis.slice(0, 60)}…`
      : undefined,
    image: work?.coverUrl ?? DEFAULT_OG_IMAGE,
    jsonLd: work ? workJsonLd(id!, work) : undefined,
  });

  const openThemes = work ? work.themeIds.filter((tid) => !work.spoilerThemeIds.includes(tid)) : [];
  const spoilerThemes = work ? work.spoilerThemeIds : [];
  const themeName = (tid: string) => work!.themeNames[work!.themeIds.indexOf(tid)];

  return (
    <div className="page">
      {state.status === "loading" && <Loading />}
      {state.status === "error" && <ErrorState error={state.error} />}
      {state.status === "ready" && !state.data && <EmptyState text="見つかりませんでした。" />}
      {state.status === "ready" && state.data && (
        <>
          <div className="work-detail__hero">
            <div className="work-detail__hero-cover">
              <WorkCover title={state.data.title} coverUrl={state.data.coverUrl} size="lg" />
              <a
                className="cover-link"
                href={amazonSearchUrl(state.data.title, state.data.authorNames[0], state.data.isbn)}
                target="_blank"
                rel="noreferrer"
              >
                Amazonで購入
              </a>
              <a
                className="cover-link"
                href={rakutenBooksUrl(state.data.title, state.data.authorNames[0], state.data.isbn, state.data.rakutenItemUrl)}
                target="_blank"
                rel="noreferrer"
              >
                楽天ブックスで購入
              </a>
            </div>
            <div className="work-card__body">
              <h1>{state.data.title}</h1>
              {state.data.originalTitle && <p className="page-subtitle">原題: {state.data.originalTitle}</p>}
              <p className="page-subtitle">
                {state.data.authorIds.map((authorId, i) => (
                  <span key={authorId}>
                    {i > 0 && "・"}
                    <Link to={`/authors/${authorId}`}>{state.data!.authorNames[i]}</Link>
                  </span>
                ))}
                {state.data.translatorIds.length > 0 && (
                  <>
                    (訳:{" "}
                    {state.data.translatorIds.map((translatorId, i) => (
                      <span key={translatorId}>
                        {i > 0 && "・"}
                        <Link to={`/translators/${translatorId}`}>{state.data!.translatorNames[i]}</Link>
                      </span>
                    ))}
                    )
                  </>
                )}
              </p>
              <p className="page-subtitle">
                <Link to={`/publishers/${state.data.publisherId}`}>{state.data.publisherName}</Link>
                {" / "}
                {state.data.firstPublishedYear}年
                {state.data.jpPublishedYear && `(邦訳${state.data.jpPublishedYear}年)`}
                {state.data.volumeCount != null && state.data.volumeCount > 1 && (
                  <>
                    {" / "}全{state.data.volumeCount}巻 / {STATUS_LABEL[state.data.status]}
                  </>
                )}
                {state.data.mediaMix?.movie && " / 映画化"}
                {state.data.mediaMix?.drama && " / ドラマ化"}
                {state.data.mediaMix?.anime && " / アニメ化"}
                {state.data.mediaMix?.comic && " / コミカライズ"}
              </p>
              {state.data.seriesName && (
                <p className="page-subtitle">
                  <Link to={`/series/${encodeURIComponent(state.data.seriesName)}`}>
                    {state.data.seriesName}
                  </Link>
                </p>
              )}

              {openThemes.length > 0 && (
                <div className="chip-row">
                  {openThemes.map((themeId) => (
                    <Link className="chip" to={`/themes/${themeId}`} key={themeId}>
                      {themeName(themeId)}
                    </Link>
                  ))}
                </div>
              )}

              {spoilerThemes.length > 0 && (
                <div className="spoiler-block">
                  {spoilersShown ? (
                    <>
                      <p className="spoiler-block__note">ネタバレを含むタグ</p>
                      <div className="chip-row">
                        {spoilerThemes.map((themeId) => (
                          <Link className="chip spoiler-chip" to={`/themes/${themeId}`} key={themeId}>
                            {themeName(themeId)}
                          </Link>
                        ))}
                      </div>
                    </>
                  ) : (
                    <button type="button" className="spoiler-toggle" onClick={() => setSpoilersShown(true)}>
                      ネタバレを含むタグを表示({spoilerThemes.length}件)
                    </button>
                  )}
                </div>
              )}

              {state.data.awardSummaries.length > 0 && (
                <div className="chip-row">
                  {state.data.awardSummaries.map((a) => (
                    <Link className="chip award-chip" to={`/awards/${a.awardId}`} key={`${a.awardId}-${a.year}`}>
                      {a.awardName} {a.result}({a.year})
                    </Link>
                  ))}
                </div>
              )}
            </div>
          </div>

          <p>{state.data.synopsis}</p>

          {state.data.externalLinks.wikipediaUrl && (
            <p>
              <a href={state.data.externalLinks.wikipediaUrl} target="_blank" rel="noreferrer">
                Wikipediaで見る
              </a>
            </p>
          )}

          {state.data.relatedComicUrl && (
            <p>
              <a className="sister-link" href={state.data.relatedComicUrl}>
                コミカライズをまんがDBで見る →
              </a>
            </p>
          )}

          {relatedWorks.length > 0 && (
            <div className="home-section">
              <h2 className="home-section__heading font-display">この作品が好きなら</h2>
              <div className="work-grid">
                {relatedWorks.map((related) => (
                  <WorkCard key={related.id} work={related} />
                ))}
              </div>
            </div>
          )}

          <p className="source-note">{state.data.sourceNote}</p>
        </>
      )}
    </div>
  );
}
