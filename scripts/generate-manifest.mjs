// Reads public/data/source/*.json (hand-authored) and writes public/data/generated/*.json:
// denormalized, name-resolved data ready for direct rendering, plus reference-integrity
// checks so a typo'd id fails the build instead of silently rendering blank names.
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const rootDir = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const sourceDir = path.join(rootDir, "public", "data", "source");
const outDir = path.join(rootDir, "public", "data", "generated");

function readSource(name) {
  return JSON.parse(readFileSync(path.join(sourceDir, `${name}.json`), "utf-8"));
}

const works = readSource("works");
const authors = readSource("authors");
const translators = readSource("translators");
const publishers = readSource("publishers");
const themes = readSource("themes");
const awards = readSource("awards");

// Optional: built by `npm run fetch-covers` (scripts/fetch-covers.mjs), which resolves an ISBN
// and cover image URL per work via the Rakuten/BOOK☆WALKER stores, then commits the result here
// so builds stay offline/deterministic. Absent entries just mean "no cover resolved yet".
const coversCachePath = path.join(sourceDir, "covers-cache.json");
const coversCache = existsSync(coversCachePath) ? JSON.parse(readFileSync(coversCachePath, "utf-8")) : {};

const authorsById = new Map(authors.map((a) => [a.id, a]));
const translatorsById = new Map(translators.map((t) => [t.id, t]));
const publishersById = new Map(publishers.map((p) => [p.id, p]));
const themesById = new Map(themes.map((t) => [t.id, t]));
const awardsById = new Map(awards.map((a) => [a.id, a]));

const errors = [];

function checkRef(map, id, kind, workId) {
  if (!map.has(id)) errors.push(`work "${workId}": unknown ${kind} id "${id}"`);
}

for (const w of works) {
  if (!Array.isArray(w.authorIds) || w.authorIds.length === 0) {
    errors.push(`work "${w.id}": authorIds must list at least one author`);
  }
  w.authorIds.forEach((id) => checkRef(authorsById, id, "author", w.id));
  w.translatorIds.forEach((id) => checkRef(translatorsById, id, "translator", w.id));
  checkRef(publishersById, w.publisherId, "publisher", w.id);
  w.themeIds.forEach((id) => checkRef(themesById, id, "theme", w.id));
  (w.awardResults ?? []).forEach((r) => checkRef(awardsById, r.awardId, "award", w.id));

  // origin drives which translation fields are meaningful; catching a mismatch here is what
  // stops a 邦訳 work from silently rendering with no translator credit.
  if (w.origin !== "jp" && w.origin !== "overseas") {
    errors.push(`work "${w.id}": origin must be "jp" or "overseas" (got "${w.origin}")`);
  } else if (w.origin === "overseas") {
    if (w.translatorIds.length === 0) errors.push(`work "${w.id}": overseas work needs at least one translator`);
    if (!w.originalTitle) errors.push(`work "${w.id}": overseas work needs originalTitle`);
  } else {
    if (w.translatorIds.length > 0) errors.push(`work "${w.id}": domestic work must not have translators`);
    if (w.originalTitle) errors.push(`work "${w.id}": domestic work must not have originalTitle`);
    if (w.jpPublishedYear) errors.push(`work "${w.id}": domestic work must not have jpPublishedYear`);
  }
}

const workIds = new Set();
for (const w of works) {
  if (workIds.has(w.id)) errors.push(`duplicate work id "${w.id}"`);
  workIds.add(w.id);
}

for (const [label, list] of [
  ["author", authors],
  ["translator", translators],
  ["publisher", publishers],
  ["theme", themes],
  ["award", awards],
]) {
  const seen = new Set();
  for (const item of list) {
    if (seen.has(item.id)) errors.push(`duplicate ${label} id "${item.id}"`);
    seen.add(item.id);
  }
}

if (errors.length > 0) {
  console.error("generate-manifest: reference integrity errors:");
  for (const e of errors) console.error(`  - ${e}`);
  process.exit(1);
}

// ---- related works ("この作品が好きなら") ----
// Cosine similarity over IDF-weighted theme tags, plus a bonus for sharing an author.
// IDF matters because the tag vocabulary is deliberately small and reused (see CLAUDE.md
// 「テーマタグの方針」): a tag carried by hundreds of works says almost nothing about similarity,
// while a rare one is highly informative. Weighting every shared tag equally would just
// surface the most generic works on every page.
// Spoiler tags are excluded from the scoring: grouping works by twist-type tags
// would let the recommendation row itself hint at the ending, which is exactly what
// CLAUDE.md「ネタバレ方針」forbids (WorkCard already refuses to render those tags).
const RELATED_COUNT = 6;
const SAME_AUTHOR_BONUS = 0.15;

const worksById = new Map(works.map((x) => [x.id, x]));

const tagsOf = (x) => x.themeIds.filter((id) => !themesById.get(id).spoiler);

const tagDocFreq = new Map();
for (const x of works) {
  for (const t of tagsOf(x)) tagDocFreq.set(t, (tagDocFreq.get(t) ?? 0) + 1);
}
// A tag carried by every work gets idf 0 and drops out of the scoring entirely.
const tagIdf = new Map([...tagDocFreq].map(([t, df]) => [t, Math.log(works.length / df)]));

const tagNorm = new Map(
  works.map((x) => {
    let sumSquares = 0;
    for (const t of tagsOf(x)) sumSquares += tagIdf.get(t) ** 2;
    return [x.id, Math.sqrt(sumSquares)];
  }),
);

const tagToItems = new Map();
for (const x of works) {
  for (const t of tagsOf(x)) {
    if (!tagToItems.has(t)) tagToItems.set(t, []);
    tagToItems.get(t).push(x);
  }
}

function relatedIdsFor(item) {
  // Accumulate the dot product only over works that share at least one tag, rather than
  // scanning all N works for each of N works.
  const dotProducts = new Map();
  for (const t of tagsOf(item)) {
    const weight = tagIdf.get(t) ** 2;
    if (weight === 0) continue;
    for (const other of tagToItems.get(t)) {
      if (other.id === item.id) continue;
      dotProducts.set(other.id, (dotProducts.get(other.id) ?? 0) + weight);
    }
  }

  const ownAuthors = new Set(item.authorIds);

  // Same-author works are a strong recommendation even with no tag overlap, so seed them in.
  for (const other of works) {
    if (other.id === item.id || dotProducts.has(other.id)) continue;
    if (other.authorIds.some((id) => ownAuthors.has(id))) dotProducts.set(other.id, 0);
  }

  const ownNorm = tagNorm.get(item.id);
  const scored = [];
  for (const [otherId, dot] of dotProducts) {
    const other = worksById.get(otherId);
    const otherNorm = tagNorm.get(otherId);
    let score = ownNorm > 0 && otherNorm > 0 ? dot / (ownNorm * otherNorm) : 0;
    if (other.authorIds.some((id) => ownAuthors.has(id))) score += SAME_AUTHOR_BONUS;
    if (score > 0) scored.push({ id: otherId, score });
  }

  // Tie-break by id so the output (and therefore the prerendered HTML) is stable across builds.
  scored.sort((a, b) => b.score - a.score || a.id.localeCompare(b.id));
  return scored.slice(0, RELATED_COUNT).map((s) => s.id);
}

const relatedById = new Map(works.map((x) => [x.id, relatedIdsFor(x)]));

// ---- generated/works.json ----
// あらすじ・出典メモ・updatedAt はここに入れない(作品詳細ページでしか使わないのに
// works.json の3分の1を占める)。詳細ページ用は work-texts.json に分ける。
const worksGenerated = works.map(({ synopsis, sourceNote, updatedAt, ...w }) => ({
  relatedWorkIds: relatedById.get(w.id),
  ...w,
  authorNames: w.authorIds.map((id) => authorsById.get(id).name),
  translatorNames: w.translatorIds.map((id) => translatorsById.get(id).name),
  publisherName: publishersById.get(w.publisherId).name,
  themeNames: w.themeIds.map((id) => themesById.get(id).name),
  // Precomputed so WorkCard can drop spoiler chips without fetching themes.json itself.
  spoilerThemeIds: w.themeIds.filter((id) => themesById.get(id).spoiler),
  awardSummaries: (w.awardResults ?? []).map((r) => ({
    awardId: r.awardId,
    awardName: awardsById.get(r.awardId).name,
    year: r.year,
    result: r.result,
  })),
  coverUrl: coversCache[w.id]?.coverUrl ?? undefined,
  // 購入リンクを商品ページへ直リンクするために使う(covers-cache が解決したISBN)
  isbn: coversCache[w.id]?.isbn ?? undefined,
  // 楽天ブックスの商品ページURL(購入リンクの直リンク用)
  rakutenItemUrl: coversCache[w.id]?.rakutenItemUrl ?? undefined,
}));

function byPublicationYear(a, b) {
  return a.firstPublishedYear - b.firstPublishedYear;
}

// 相互参照リスト(著者・翻訳者・出版社・テーマ・シリーズの各詳細ページ)は作品を**idの配列**で持ち、
// 表示側は works.json(取得済みキャッシュ)から引き直して WorkCard を描く。
// 作品をフル展開して埋め込むと、1作品が平均8つのリストに重複して入って生成JSONが数MB膨らむ
// (ranobe-db では themes.json が 24MB になり、トップページが gzip 7.4MB を転送していた)。
const idsByPublicationYear = (list) => [...list].sort(byPublicationYear).map((w) => w.id);

// ---- generated/{authors,translators,publishers}.json ----
function buildPersonList(people, worksByPersonId) {
  return people
    .map((p) => {
      const theirWorks = worksByPersonId.get(p.id) ?? [];
      return {
        id: p.id,
        name: p.name,
        nameKana: p.nameKana,
        description: p.description,
        externalLinks: p.externalLinks,
        workCount: theirWorks.length,
        workIds: idsByPublicationYear(theirWorks),
      };
    })
    .sort((a, b) => a.nameKana.localeCompare(b.nameKana, "ja"));
}

function groupWorksBy(idsOf) {
  const map = new Map();
  for (const w of works) {
    for (const id of idsOf(w)) {
      if (!map.has(id)) map.set(id, []);
      map.get(id).push(w);
    }
  }
  return map;
}

const authorsGenerated = buildPersonList(authors, groupWorksBy((w) => w.authorIds));
const translatorsGenerated = buildPersonList(translators, groupWorksBy((w) => w.translatorIds));
const publishersGenerated = buildPersonList(
  publishers,
  groupWorksBy((w) => [w.publisherId])
);

// ---- generated/themes.json ----
const worksByTheme = groupWorksBy((w) => w.themeIds);
const themesGenerated = themes
  .map((t) => {
    const theirWorks = worksByTheme.get(t.id) ?? [];
    return {
      ...t,
      workCount: theirWorks.length,
      workIds: idsByPublicationYear(theirWorks),
    };
  })
  .sort((a, b) => b.workCount - a.workCount || a.name.localeCompare(b.name, "ja"));

// ---- generated/series.json ----
// シリーズはエンティティではなく works.json の seriesName(自由文)から組み立てる。
// 1作しかないシリーズもページは作る(続刊が入ったときに同じURLがそのまま育つ)が、
// 一覧の既定表示と絞り込みの選択肢には2作以上のものだけを出す。
const worksBySeries = groupWorksBy((w) => (w.seriesName ? [w.seriesName] : []));
const seriesGenerated = [...worksBySeries.entries()]
  .map(([name, theirWorks]) => ({
    id: name,
    name,
    workCount: theirWorks.length,
    // シリーズ内は刊行順で読むものなので、他のページと違って古い順に固定する。
    workIds: idsByPublicationYear(theirWorks),
  }))
  .sort((a, b) => b.workCount - a.workCount || a.name.localeCompare(b.name, "ja"));

// ---- generated/recommend-index.json ----
// 「好みからおすすめ」(/recommend)専用の軽量索引。テーマ選択チップとスコア計算に必要な分だけ。
// themes.json / works.json を選択前に読ませないためにこれがある。
// **読み手は /recommend だけ。ページを消すならこの生成も消すこと**(横断検索を消したとき、
// 専用の search-index.json が読み手のいないまま残りかけた)。
//
// spoiler テーマは選択肢からも作品側の集計からも外す。関連作品のスコア計算(relatedIdsFor)が
// spoiler を除いているのと同じ理由で、タグの重なりから真相が透けるのを避ける。
const recommendTagIds = new Set(themes.filter((t) => !t.spoiler).map((t) => t.id));
const recommendIndex = {
  tags: themesGenerated
    .filter((t) => t.workCount > 0 && recommendTagIds.has(t.id))
    .map((t) => ({ id: t.id, name: t.name, count: t.workCount })),
  items: works.map((w) => ({
    id: w.id,
    tagIds: w.themeIds.filter((t) => recommendTagIds.has(t)),
  })),
};

// ---- generated/work-texts.json ----
// 作品詳細ページだけが読む長文(あらすじ・出典メモ)。キーは作品id。
const workTexts = Object.fromEntries(
  works.map((w) => [w.id, { synopsis: w.synopsis, sourceNote: w.sourceNote }]),
);

// ---- generated/awards.json ----
// 受賞歴の result は「2013年版 国内編 第1位」「大賞」「第5位」のような自由文なので、
// 並べ替え用の順位をここで一度だけ取り出す。順位を持たない賞(大賞・特別賞など)は
// 大賞系を先頭、それ以外を末尾に置く。
function rankOf(result) {
  const m = /第\s*(\d+)\s*位/.exec(result ?? "");
  if (m) return Number(m[1]);
  if (/大賞|1位|第一位/.test(result ?? "")) return 0;
  return 900;
}

const winnersByAward = new Map();
for (const w of works) {
  for (const r of w.awardResults ?? []) {
    if (!winnersByAward.has(r.awardId)) winnersByAward.set(r.awardId, []);
    winnersByAward.get(r.awardId).push({
      workId: w.id,
      workTitle: w.title,
      year: r.year,
      result: r.result,
      rank: rankOf(r.result),
    });
  }
}
const awardsGenerated = awards
  .map((a) => {
    // 年の降順 → 部門(result から順位表記を除いた部分)→ 順位の昇順。
    // 部門を先に見るのは、国内編と海外編が1位・1位・2位・2位…と交互に並ぶのを避けるため。
    const section = (r) => (r.result ?? "").replace(/第\s*\d+\s*位.*$/, "").trim();
    const winners = (winnersByAward.get(a.id) ?? []).sort(
      (x, y) =>
        y.year - x.year ||
        section(x).localeCompare(section(y), "ja") ||
        x.rank - y.rank ||
        x.workTitle.localeCompare(y.workTitle, "ja"),
    );
    return { ...a, workCount: winners.length, winners };
  })
  // 受賞作の多い賞ほど見たい情報なので件数の降順。同数は名前順で並びを安定させる。
  .sort((a, b) => b.workCount - a.workCount || a.name.localeCompare(b.name, "ja"));

// ---- generated/counts.json ----
const counts = {
  works: works.length,
  authors: authors.length,
  translators: translators.length,
  publishers: publishers.length,
  themes: themes.length,
  awards: awards.length,
  // トップのバッジは /series の既定表示(2作以上)と数を揃える。
  // 1作だけのシリーズもページは持つが、一覧では畳んでいるため。
  series: seriesGenerated.filter((x) => x.workCount > 1).length,
};

mkdirSync(outDir, { recursive: true });
writeFileSync(path.join(outDir, "works.json"), JSON.stringify(worksGenerated), "utf-8");
writeFileSync(path.join(outDir, "authors.json"), JSON.stringify(authorsGenerated), "utf-8");
writeFileSync(path.join(outDir, "translators.json"), JSON.stringify(translatorsGenerated), "utf-8");
writeFileSync(path.join(outDir, "publishers.json"), JSON.stringify(publishersGenerated), "utf-8");
writeFileSync(path.join(outDir, "themes.json"), JSON.stringify(themesGenerated), "utf-8");
writeFileSync(path.join(outDir, "awards.json"), JSON.stringify(awardsGenerated), "utf-8");
writeFileSync(path.join(outDir, "recommend-index.json"), JSON.stringify(recommendIndex), "utf-8");
writeFileSync(path.join(outDir, "work-texts.json"), JSON.stringify(workTexts), "utf-8");
writeFileSync(path.join(outDir, "series.json"), JSON.stringify(seriesGenerated), "utf-8");
writeFileSync(path.join(outDir, "counts.json"), JSON.stringify(counts), "utf-8");

console.log(
  `generate-manifest: wrote ${works.length} works, ${authors.length} authors, ${translators.length} translators, ${publishers.length} publishers, ${themes.length} themes, ${awards.length} awards, ${seriesGenerated.length} series`
);


// ---- sitemap.xml ----
// Lives at the site root (not data/generated/) so it's served at /sf-db/sitemap.xml, but is
// just as deterministically derived from public/data/source/*.json — see the .gitignore note.
const SITE_URL = "https://izenmi.github.io/sf-db";
const today = new Date().toISOString().slice(0, 10);

function urlEntry(loc, lastmod) {
  return `  <url>\n    <loc>${SITE_URL}${loc}</loc>\n    <lastmod>${lastmod ?? today}</lastmod>\n  </url>`;
}

const sitemapEntries = [
  urlEntry("/"),
  urlEntry("/works"),
  ...works.map((w) => urlEntry(`/works/${w.id}`, w.updatedAt?.slice(0, 10))),
  urlEntry("/themes"),
  urlEntry("/recommend"),
  ...themes.map((t) => urlEntry(`/themes/${t.id}`)),
  urlEntry("/authors"),
  ...authors.map((a) => urlEntry(`/authors/${a.id}`, a.updatedAt?.slice(0, 10))),
  urlEntry("/translators"),
  ...translators.map((t) => urlEntry(`/translators/${t.id}`, t.updatedAt?.slice(0, 10))),
  urlEntry("/publishers"),
  ...publishers.map((p) => urlEntry(`/publishers/${p.id}`, p.updatedAt?.slice(0, 10))),
  urlEntry("/awards"),
  ...awards.map((a) => urlEntry(`/awards/${a.id}`, a.updatedAt?.slice(0, 10))),
  urlEntry("/series"),
  // シリーズ名は日本語なので、sitemap に載せるURLはパーセントエンコードする
  ...seriesGenerated.map((x) => urlEntry(`/series/${encodeURIComponent(x.id)}`)),
  urlEntry("/about"),
];

const sitemapXml =
  `<?xml version="1.0" encoding="UTF-8"?>\n` +
  `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${sitemapEntries.join("\n")}\n</urlset>\n`;

writeFileSync(path.join(rootDir, "public", "sitemap.xml"), sitemapXml, "utf-8");
console.log(`generate-manifest: wrote sitemap.xml with ${sitemapEntries.length} URLs`);
