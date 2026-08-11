import { useState } from "react";

const COVER_COLORS = ["blue", "pink", "mint", "yellow", "peach", "purple"] as const;

function colorFor(title: string): (typeof COVER_COLORS)[number] {
  let sum = 0;
  for (let i = 0; i < title.length; i++) sum += title.charCodeAt(i);
  return COVER_COLORS[sum % COVER_COLORS.length];
}

/** Real cover image when one was resolved (public/data/source/covers-cache.json, built by
 *  `npm run fetch-covers` — see scripts/fetch-covers.mjs), falling back to a generated
 *  placeholder (title on a pastel card) when absent or the image fails to load. We don't host
 *  cover art ourselves; that's copyrighted illustration work, not a fact. */
/** 楽天のサムネイル(thumbnail.image.rakuten.co.jp)は `?_ex=WxH` で任意サイズを返す。
 *  covers-cache に入っているURLは小さいカード用の 400x400 なので、184x262 で並べる表紙表示では
 *  そのままだと粗い。表示時にURLを書き換えるだけで済むため、書影の再取得は不要。
 *  `_ex` を持たないURL(BOOK☆WALKER・honto)は不一致で素通りする。 */
function coverSrc(coverUrl: string, size: string): string {
  return size === "xl" ? coverUrl.replace(/([?&]_ex=)\d+x\d+/, "$1600x600") : coverUrl;
}

export function WorkCover({
  title,
  coverUrl,
  size = "sm",
}: {
  title: string;
  coverUrl?: string;
  size?: "sm" | "lg" | "xl";
}) {
  const [broken, setBroken] = useState(false);
  if (coverUrl && !broken) {
    return (
      <img
        className={`work-cover work-cover--${size} work-cover--image`}
        src={coverSrc(coverUrl, size)}
        alt={title}
        loading="lazy"
        onError={() => setBroken(true)}
      />
    );
  }
  return (
    <div className={`work-cover work-cover--${size} work-cover--${colorFor(title)}`}>
      <span className="work-cover__title">{title}</span>
    </div>
  );
}

const AMAZON_AFFILIATE_TAG = "izenmi-22";

/** 楽天アフィリエイトID(affiliate.rakuten.co.jp で発行される4ブロックの文字列)。
 *  アフィリエイトIDは公開前提の識別子なのでフロントに直書きしてよい(楽天ウェブサービスの
 *  accessKey とは別物。あちらは秘匿情報なので絶対にここへ置かない)。
 *  空文字のあいだは素の楽天ブックスURLを返すので、未設定でもリンクは壊れない。 */
const RAKUTEN_AFFILIATE_ID = "563a399e.14e18d72.563a399f.79fc1b6e";

/** ISBN-13(978始まり)をISBN-10へ変換する。書籍のAmazon ASINはISBN-10と一致するので、
 *  これで商品ページへ直リンクできる。979始まり(ISBN-10が存在しない)は null を返す。 */
function isbn13to10(isbn13?: string): string | undefined {
  if (!isbn13) return undefined;
  const d = isbn13.replace(/[^0-9Xx]/g, "");
  if (d.length !== 13 || !d.startsWith("978")) return undefined;
  const core = d.slice(3, 12);
  let sum = 0;
  for (let i = 0; i < 9; i++) sum += (10 - i) * Number(core[i]);
  const check = (11 - (sum % 11)) % 11;
  return core + (check === 10 ? "X" : String(check));
}

/** Amazonへの購入リンク。ISBNが分かっている作品は商品ページ(/dp/<ISBN-10>)へ直リンクし、
 *  分からない場合は検索結果へ落とす。`extra`(著者名など)は短い一般的なタイトルの絞り込み用。 */
export function amazonSearchUrl(title: string, extra?: string, isbn?: string): string {
  const asin = isbn13to10(isbn);
  if (asin) return `https://www.amazon.co.jp/dp/${asin}/?tag=${AMAZON_AFFILIATE_TAG}`;
  const query = extra ? `${title} ${extra}` : title;
  const params = new URLSearchParams({ k: query, tag: AMAZON_AFFILIATE_TAG });
  return `https://www.amazon.co.jp/s?${params.toString()}`;
}

/** 楽天ブックスへの購入リンク。ISBNがあればISBN検索(その本に直行する)、なければタイトル+著者検索。
 *  RAKUTEN_AFFILIATE_ID が設定されていれば hb.afl.rakuten.co.jp のアフィリエイトリンクで包む。 */
export function rakutenBooksUrl(title: string, extra?: string, isbn?: string, itemUrl?: string): string {
  // 商品ページURL(scripts/fetch-rakuten-links.mjs が covers-cache に保存したもの)があれば直リンク。
  // 無ければISBN検索 → タイトル+著者検索の順に落とす。
  const target =
    itemUrl ??
    `https://books.rakuten.co.jp/search?sitem=${encodeURIComponent(
      isbn ? isbn.replace(/[^0-9Xx]/g, "") : extra ? `${title} ${extra}` : title,
    )}`;
  if (!RAKUTEN_AFFILIATE_ID) return target;
  const encoded = encodeURIComponent(target);
  return `https://hb.afl.rakuten.co.jp/hgc/${RAKUTEN_AFFILIATE_ID}/?pc=${encoded}&m=${encoded}`;
}
