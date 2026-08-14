// Resolves a representative ISBN + cover image URL per work via the Rakuten Books search API
// (BooksTotal/Search) and caches the result in public/data/source/covers-cache.json (committed,
// read by generate-manifest.mjs). Not run on every build — run manually with `npm run
// fetch-covers` when adding new works or retrying misses. Each work here is a single novel, so
// this searches by its 邦題 (never the original title — Japanese stores don't index those) and
// keeps items that look like an actual edition of that book: non-empty isbn (Blu-ray/DVD/CD items
// use `jan` instead), a title matching the work's, and an author that matches ours.
//
// **Every match path requires the author name to appear in the store's metadata.** Mystery titles
// are short and generic in a way light-novel titles aren't (『点と線』『火車』『霧の旗』), and
// prefix matching alone pulls in unrelated books, novelizations of same-titled films, and manga
// adaptations. This mirrors what manga-db had to do for the same reason.
//
// We tried openBD first (ISBN -> cover), but its cover images only come from 版元ドットコム
// member publishers, so real-world coverage was ~0%. Rakuten Books actually sells these titles,
// so its own cover images are far more complete.
//
// Three sources are tried in order, each with the same keyword candidates (see keywordCandidates):
//
//   1. Rakuten Books (BooksTotal/Search) — print editions. Strongest tier for this genre, since
//      mystery novels have deep print backlists (単行本 + 文庫) unlike web-novel-derived titles.
//   2. Rakuten Kobo (Kobo/EbookSearch) — same app credentials. Covers titles Rakuten doesn't
//      stock in print. Kobo items have no ISBN field (itemNumber instead), so these are cached
//      with isbn: null and source: "kobo".
//   3. BOOK☆WALKER (HTML). No public API, but both the search page and the product pages are
//      server-rendered: the search page links to https://bookwalker.jp/de<uuid>/ (and returns
//      HTTP 404 when there are zero hits, which is a clean "no results" signal), and each product
//      page carries <meta property="og:image"> plus a <title> of the form
//        <作品名> - <ジャンル> <著者>（<レーベル>）：電子書籍試し読み無料 - BOOK☆WALKER -
//      i.e. genre, author and label in one string. bookwalker.jp/robots.txt allows /search/ and
//      /de*/ (it only disallows /member/, /history/ and friends), and c.bookwalker.jp serves the
//      images without any Referer restriction. Cached with isbn: null and source: "bookwalker".
//
// BOOK☆WALKER's raw search ranking is NOT trustworthy — a zero-hit query falls back to unrelated
// promoted items, and manga adaptations of the same series rank above the novel. So a candidate is
// only accepted when its genre isn't マンガ（漫画）/ライトノベル/実用/etc., an author name from
// authors.json appears in the page title, AND the normalized core title is contained in it.
//
// Cover URLs are always harvested from a real page (API response / og:image). Guessing or
// hardcoding a direct image URL by pattern is still forbidden.
//
// Requires a Rakuten Web Service app — free, instant self-serve: register at
// https://webservice.rakuten.co.jp/ and copy its "アプリケーションID" and "アクセスキー". Pass
// them via env vars; never commit them. The current gateway credentials are shared across all
// four sister sites (verified 2026-08-04), so ranobe-db's keys work here as-is. The API enforces
// Referer/Origin headers — see REFERER_URL below — which this script sends explicitly since it
// isn't a browser request.
//
// Usage:
//   RAKUTEN_APP_ID=xxx RAKUTEN_ACCESS_KEY=xxx npm run fetch-covers
//   RAKUTEN_APP_ID=xxx RAKUTEN_ACCESS_KEY=xxx npm run fetch-covers -- --force
//   RAKUTEN_APP_ID=xxx RAKUTEN_ACCESS_KEY=xxx npm run fetch-covers -- --retry-misses
//   RAKUTEN_APP_ID=xxx RAKUTEN_ACCESS_KEY=xxx npm run fetch-covers -- --only=ten-to-sen,kasha
//
// --force re-fetches everything, including entries that were filled in by hand, so prefer
// --retry-misses when you just want to have another go at the unresolved works: it only touches
// entries whose coverUrl is null and leaves every resolved entry alone.
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const rootDir = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const sourceDir = path.join(rootDir, "public", "data", "source");
const worksPath = path.join(sourceDir, "works.json");
const authorsPath = path.join(sourceDir, "authors.json");
const cachePath = path.join(sourceDir, "covers-cache.json");

const REFERER_URL = "https://izenmi.github.io/sf-db/";
const ORIGIN_URL = "https://izenmi.github.io";
const BROWSER_UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

/** How many BOOK☆WALKER product pages to open per search (each one is an extra HTTP request). */
const BW_PRODUCT_LIMIT = 4;

// Only the two Rakuten tiers need credentials; BOOK☆WALKER is plain HTML. Running without them
// is therefore useful (BOOK☆WALKER-only pass) rather than fatal.
const APP_ID = process.env.RAKUTEN_APP_ID;
const ACCESS_KEY = process.env.RAKUTEN_ACCESS_KEY;
const RAKUTEN_ENABLED = Boolean(APP_ID && ACCESS_KEY);
if (!RAKUTEN_ENABLED) {
  console.warn(
    "RAKUTEN_APP_ID / RAKUTEN_ACCESS_KEY が未設定のため、楽天ブックス・Koboをスキップし BOOK☆WALKER のみで解決します(see the header comment in this file)。",
  );
}

const works = JSON.parse(readFileSync(worksPath, "utf-8"));
const authors = JSON.parse(readFileSync(authorsPath, "utf-8"));
const cache = existsSync(cachePath) ? JSON.parse(readFileSync(cachePath, "utf-8")) : {};

const authorNameById = new Map(authors.map((a) => [a.id, a.name]));

const args = process.argv.slice(2);
const FORCE = args.includes("--force");
const RETRY_MISSES = args.includes("--retry-misses");
const onlyArg = args.find((a) => a.startsWith("--only="));
const ONLY = onlyArg ? onlyArg.slice("--only=".length).split(",") : undefined;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// NFKC folds the fullwidth/halfwidth variants that Japanese book catalogs mix freely (ＴＥＮＫＹ
// vs TENKY, （） vs (), U+FF5E ～ vs ~). The explicit class then drops the punctuation that
// differs between our titles and a store's — including the wave dash U+301C 〜, which NFKC does
// NOT fold into U+FF5E and which used to silently break prefix matching on subtitled titles.
function normalize(title) {
  return title
    .normalize("NFKC")
    .replace(/[\s　・:：;；!?！？―—\-ー~〜～()（）「」『』【】〈〉《》〔〕"“”'’,、.。]/g, "")
    .toLowerCase();
}

// The part of a series title a store is likely to index under: everything before the long
// subtitle that web-novel titles carry (`～…～`, `（…）`, `【…】`), minus quoting brackets and a
// trailing "シリーズ" that only exists in our own data (e.g. 「文学少女」シリーズ -> 文学少女).
function coreTitle(title) {
  return title
    .split(/[~〜～(（【]/)[0]
    .replace(/[「」『』"“”]/g, "")
    .replace(/シリーズ$/, "")
    .trim();
}

function authorNamesFor(work) {
  return (work.authorIds ?? []).map((id) => authorNameById.get(id)).filter(Boolean);
}

// Progressively looser search keywords. The full title is the most precise; the core title finds
// entries whose subtitle is punctuated differently; adding the author disambiguates a core title
// that is too generic on its own. Anything matched on one of the looser keywords has to pass the
// author check as well (see pickBestMatch), so widening the net here doesn't widen false matches.
function keywordCandidates(work, authorNames) {
  const core = coreTitle(work.title);
  const candidates = [work.title, core];
  if (authorNames.length > 0) candidates.push(`${core || work.title} ${authorNames[0]}`);
  return [...new Set(candidates.filter(Boolean))];
}

function authorMatches(text, authorNames) {
  if (authorNames.length === 0) return false;
  const haystack = normalize(text ?? "");
  return authorNames.some((name) => haystack.includes(normalize(name)));
}

// Items that are about the series rather than a volume of it. Their "cover" is an art-book jacket
// or a photo of a shrink-wrapped box set, which looks worse than this site's own placeholder card.
const NON_VOLUME_PATTERNS =
  /画集|イラスト集|設定資料|ファンブック|アンソロジー|全巻セット|完結セット|セット\s*$|大全集|短編集|傑作選|データ集|ガイドブック|ムック|カレンダー/;

/**
 * Orders otherwise-equal candidates: a volume 1 beats an unnumbered volume, which beats volume 12.
 * Any volume's art is still the right series, so this is a preference, not a filter.
 */
function volumeRank(title) {
  const t = title.normalize("NFKC");
  if (/[（([\s　]0?1[）)\]\s　]|[（(]0?1[）)]|\s0?1$/.test(t)) return 0;
  if (!/\d/.test(t)) return 1;
  return 2;
}

/** Applies the shared "is this actually a volume of the series" filter and best-first ordering. */
function rankCandidates(items, titleOf) {
  return items
    .filter((it) => !NON_VOLUME_PATTERNS.test(titleOf(it) ?? ""))
    .sort((a, b) => volumeRank(titleOf(a) ?? "") - volumeRank(titleOf(b) ?? ""));
}

/** Rakuten serves a generic grey placeholder for items with no real cover — never cache one. */
function isPlaceholderImage(imageUrl) {
  return !imageUrl || /noimage/i.test(imageUrl);
}

/** Bump the thumbnail service's requested resolution (default 200x200) for a crisper cover. */
function upscale(imageUrl) {
  return imageUrl.replace(/_ex=\d+x\d+/, "_ex=400x400");
}

// Rakuten answers 429 when a long batch runs (or when a sister site's fetch-covers runs at the
// same time on the same app credentials). Backing off once or twice keeps a run from dropping
// entries — a thrown error leaves the work unresolved until the next --retry-misses pass.
async function fetchRakuten(url) {
  for (let attempt = 0; ; attempt++) {
    const res = await fetch(url, { headers: { Referer: REFERER_URL, Origin: ORIGIN_URL } });
    if (res.status !== 429 || attempt >= 2) return res;
    await sleep(5000 * (attempt + 1));
  }
}

async function searchRakuten(keyword) {
  const params = new URLSearchParams({
    applicationId: APP_ID,
    accessKey: ACCESS_KEY,
    keyword,
    hits: "30",
    sort: "+releaseDate",
    format: "json",
  });
  const url = `https://openapi.rakuten.co.jp/services/api/BooksTotal/Search/20170404?${params.toString()}`;
  const res = await fetchRakuten(url);
  const data = await res.json();
  if (!res.ok || data.errors) {
    throw new Error(data.errors?.errorMessage || data.error_description || `HTTP ${res.status}`);
  }
  return (data.Items ?? []).map((wrapped) => wrapped.Item);
}

// Fallback for series Rakuten Books doesn't carry (small-press / web-novel-origin titles that
// only ship as e-books). Same app credentials work across Rakuten Web Service APIs. Kobo items
// have no ISBN field (itemNumber instead), so these are cached with isbn: null.
async function searchKobo(keyword) {
  const params = new URLSearchParams({
    applicationId: APP_ID,
    accessKey: ACCESS_KEY,
    keyword,
    hits: "30",
    sort: "+releaseDate",
    format: "json",
  });
  const url = `https://openapi.rakuten.co.jp/services/api/Kobo/EbookSearch/20170426?${params.toString()}`;
  const res = await fetchRakuten(url);
  const data = await res.json();
  if (!res.ok || data.errors) {
    throw new Error(data.errors?.errorMessage || data.error_description || `HTTP ${res.status}`);
  }
  return (data.Items ?? []).map((wrapped) => wrapped.Item);
}

function pickBestMatch(items, work, authorNames) {
  const target = normalize(work.title);
  const core = normalize(coreTitle(work.title));
  // Already sorted oldest-first by the API (sort=+releaseDate). Require a 978-4 (Japan
  // registrant group) ISBN, and exclude the コミック (001001) and ライトノベル (001017) top-level
  // genres so a same-titled comic adaptation or light novel can't outrank the mystery itself.
  //
  // The author check applies to BOTH match paths here, unlike ranobe-db where it only guards the
  // loose one: `点と線` or `火車` as a bare prefix matches plenty of unrelated books.
  const eligible = rankCandidates(
    items.filter(
      (it) =>
        it.isbn &&
        it.isbn.startsWith("9784") &&
        !(it.booksGenreId ?? "").startsWith("001001") &&
        !(it.booksGenreId ?? "").startsWith("001017") &&
        !isPlaceholderImage(it.largeImageUrl) &&
        authorMatches(`${it.title ?? ""} ${it.author ?? ""}`, authorNames),
    ),
    (it) => it.title,
  );
  return (
    eligible.find((it) => normalize(it.title ?? "").startsWith(target)) ??
    // Looser: the store's title merely contains our core title.
    eligible.find((it) => core.length >= 3 && normalize(it.title ?? "").includes(core))
  );
}

function pickBestKoboMatch(items, work, authorNames) {
  const target = normalize(work.title);
  const core = normalize(coreTitle(work.title));
  const eligible = rankCandidates(
    items.filter(
      (it) =>
        !isPlaceholderImage(it.largeImageUrl) &&
        authorMatches(`${it.title ?? ""} ${it.author ?? ""}`, authorNames),
    ),
    (it) => it.title,
  );
  return (
    eligible.find((it) => normalize(it.title ?? "").startsWith(target)) ??
    eligible.find((it) => core.length >= 3 && normalize(it.title ?? "").includes(core))
  );
}

function decodeEntities(text) {
  return text
    .replace(/&#0?39;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&");
}

async function fetchHtml(url) {
  const res = await fetch(url, { headers: { "User-Agent": BROWSER_UA } });
  if (res.status === 404) return null; // BOOK☆WALKER answers 404 for a zero-hit search
  if (!res.ok) throw new Error(`HTTP ${res.status} (${url})`);
  return res.text();
}

// Returns the product pages behind a BOOK☆WALKER search, each with its <title> (genre + author +
// label) and og:image (the cover). Empty array when the search has no hits.
async function searchBookWalker(keyword) {
  const html = await fetchHtml(`https://bookwalker.jp/search/?word=${encodeURIComponent(keyword)}`);
  if (!html) return [];
  const links = [
    ...new Set([...html.matchAll(/href="(https:\/\/bookwalker\.jp\/de[0-9a-f-]+\/)"/g)].map((m) => m[1])),
  ];
  const candidates = [];
  for (const link of links.slice(0, BW_PRODUCT_LIMIT)) {
    await sleep(1500);
    let page;
    try {
      page = await fetchHtml(link);
    } catch {
      continue;
    }
    if (!page) continue;
    const image = page.match(/<meta property="og:image" content="([^"]+)"/)?.[1];
    if (!image) continue;
    const pageTitle = decodeEntities(page.match(/<title>([\s\S]*?)<\/title>/)?.[1] ?? "");
    const ogTitle = decodeEntities(page.match(/<meta property="og:title" content="([^"]+)"/)?.[1] ?? "");
    candidates.push({ url: link, pageTitle, title: ogTitle || pageTitle.split(" - ")[0], image });
  }
  return candidates;
}

/** The genre token of a BOOK☆WALKER <title>: "<作品名> - <ジャンル> <著者>（<レーベル>）：…". */
function bookWalkerGenre(pageTitle) {
  return pageTitle.split(" - ")[1]?.split(/[\s　]/)[0] ?? "";
}

const BW_REJECTED_GENRES = ["マンガ（漫画）", "ライトノベル", "実用", "ゲーム攻略本", "雑誌", "写真集"];

/** Art books and omnibus editions are real hits but poor series covers — only used as a last resort. */
function bookWalkerPenalty(title) {
  return /合本版|artworks|art works|画集|イラスト集|設定資料|アンソロジー/i.test(title) ? 1 : 0;
}

function pickBestBookWalkerMatch(candidates, work, authorNames) {
  const core = normalize(coreTitle(work.title));
  if (core.length < 3) return undefined;
  const usable = candidates.filter(
    (c) =>
      !BW_REJECTED_GENRES.includes(bookWalkerGenre(c.pageTitle)) &&
      authorMatches(c.pageTitle, authorNames) &&
      normalize(c.pageTitle).includes(core),
  );
  return usable.sort(
    (a, b) => bookWalkerPenalty(a.title) - bookWalkerPenalty(b.title) || volumeRank(a.title) - volumeRank(b.title),
  )[0];
}

// Walks the three sources in order, retrying each with progressively looser keywords before
// moving on. Returns the cache entry to store, or null when nothing matched anywhere.
async function resolveWork(work) {
  const authorNames = authorNamesFor(work);
  const keywords = keywordCandidates(work, authorNames);

  for (const keyword of RAKUTEN_ENABLED ? keywords : []) {
    const items = await searchRakuten(keyword);
    await sleep(1100);
    const best = pickBestMatch(items, work, authorNames);
    if (best) {
      console.log(`[ok] ${work.title} -> matched "${best.title}" (ISBN ${best.isbn})`);
      return {
        title: work.title,
        isbn: best.isbn,
        matchedTitle: best.title,
        coverUrl: best.largeImageUrl ? upscale(best.largeImageUrl) : null,
        source: "rakuten-books",
        resolvedAt: new Date().toISOString(),
      };
    }
  }

  for (const keyword of RAKUTEN_ENABLED ? keywords : []) {
    const items = await searchKobo(keyword);
    await sleep(1100);
    const best = pickBestKoboMatch(items, work, authorNames);
    if (best) {
      console.log(`[ok-kobo] ${work.title} -> matched "${best.title}" (Kobo電子書籍)`);
      return {
        title: work.title,
        isbn: null,
        matchedTitle: best.title,
        coverUrl: best.largeImageUrl || null,
        source: "kobo",
        resolvedAt: new Date().toISOString(),
      };
    }
  }

  for (const keyword of keywords) {
    const candidates = await searchBookWalker(keyword);
    await sleep(1500);
    const best = pickBestBookWalkerMatch(candidates, work, authorNames);
    if (best) {
      console.log(`[ok-bw] ${work.title} -> matched "${best.title}" (BOOK☆WALKER)`);
      return {
        title: work.title,
        isbn: null,
        matchedTitle: best.title,
        coverUrl: best.image,
        source: "bookwalker",
        resolvedAt: new Date().toISOString(),
      };
    }
  }

  return null;
}

function shouldSkip(work) {
  const cached = cache[work.id];
  if (!cached) return false;
  if (FORCE) return false;
  if (RETRY_MISSES) return Boolean(cached.coverUrl);
  return true;
}


/**
 * 解決できなかったときのキャッシュ更新。
 *
 * 前のエントリがあるなら、分かっていること(ISBN・購入リンク・手書き注記・すでに持っている
 * 表紙)はそのまま残し、「いつ試したか」だけを更新する。今回分かったのは「見つからなかった」
 * ことだけで、前に分かっていたことが嘘になったわけではない。
 * 全部を null の雛形で上書きすると、手で直した判断が再取得のたびに消える。
 */
function keepWhatWeKnew(previous, fallback) {
  if (!previous) return fallback;
  return { ...previous, resolvedAt: new Date().toISOString() };
}

/** 自動取得が成功したときも、手書きの注記だけは引き継ぐ。 */
function withNote(previous, entry) {
  return previous?.note && !entry.note ? { ...entry, note: previous.note } : entry;
}

async function run() {
  const targets = works.filter((w) => (ONLY ? ONLY.includes(w.id) : true));
  let updated = 0;
  let skipped = 0;
  let missed = 0;

  for (const work of targets) {
    if (shouldSkip(work)) {
      skipped++;
      continue;
    }
    try {
      const entry = await resolveWork(work);
      if (entry) {
        cache[work.id] = withNote(cache[work.id], entry);
        updated++;
      } else {
        cache[work.id] = keepWhatWeKnew(cache[work.id], { title: work.title, isbn: null, coverUrl: null, resolvedAt: new Date().toISOString() });
        console.log(`[miss] ${work.title}: 楽天ブックス・Kobo・BOOK☆WALKERのいずれにも該当書誌が見つかりませんでした`);
        missed++;
      }
    } catch (err) {
      console.error(`[error] ${work.title}: ${err.message}`);
    }
  }

  const sorted = Object.fromEntries(Object.entries(cache).sort(([a], [b]) => a.localeCompare(b)));
  writeFileSync(cachePath, JSON.stringify(sorted, null, 2) + "\n");
  console.log(`完了: ${updated}件更新, ${missed}件未解決, ${skipped}件スキップ(既存キャッシュ)。 -> ${cachePath}`);
}

run();
