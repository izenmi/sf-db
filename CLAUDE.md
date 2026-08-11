# sf-db

国内外のSF小説を著者・翻訳者・出版社・受賞歴・テーマから検索できるファンデータベース。姉妹サイト[ミステリDB](https://izenmi.github.io/mystery-db/)(`izenmi/mystery-db`)のSF版として、mystery-dbをscaffoldコピーして作成した(2026-08-11)。mystery-dbとの最大の違いは**探偵(detective)エンティティを持たない**こと。それ以外のアーキテクチャ・デザインシステム・運用ノウハウはmystery-db(さらに遡ればranobe-db)と共通なので、**ここに書いていない運用の詳細はmystery-dbのCLAUDE.mdを参照**してよい(スクリプトの使い方・裏取りの型・表紙の誤マッチ類型はほぼそのまま通用する)。

- 公開URL: https://izenmi.github.io/sf-db/
- リポジトリ: `izenmi/sf-db`(public。GitHub Pagesは無料枠だとpublicでないと使えない)
- スタック: React 18 + TypeScript + Vite 5 + `react-router-dom`(`BrowserRouter`)

## 収録方針(2026-08-11にユーザーと合意)

- **SF小説のみ**。映画・アニメ・ゲームのSFは姉妹サイト(movie-db/anime-db/game-db)が担当するため収録しない
- **国内SF+海外SFの邦訳**。日本語で読めることが条件(未訳作品は収録しない)
- ノベライズは収録対象(ガイドブック等の非小説だけ除く。2026-08-09の姉妹サイト共通指示)
- SFとライトノベル・ミステリーの境界作品は重複収録を許容する(姉妹サイト間の重複チェックはしない方針)

## ネタバレ方針(mystery-dbから継承、SF向けに基準を書き直し)

- **あらすじ・`sourceNote`に、物語の真相・どんでん返しの核心を書かない**。あらすじは「読者が本を手に取るかどうか判断できる情報」までにとどめる
- **`ThemeSource.spoiler: true` を付ける基準**: 「そのタグが作品に付いていることを知ること自体が、結末の仕掛けを割るもの」だけ。帯・あらすじ・レーベルの惹句で公表されている構造タグは対象外
  - spoiler扱いにする例: 叙述トリックSF、世界の真相もの(舞台・語り手の正体が仕掛けの作品)
  - spoiler扱いにしない例: タイムループ、ディストピア、ポストアポカリプス(いずれも売り文句として表に出る)
  - **タグ名単体でネタバレにならない命名にする**(「実は〇〇だった」のような具体的な名前を付けない)
- UI側の実装(mystery-dbと同一): `WorkCard`はspoilerタグを描画しない / `WorkDetailPage`はボタン展開(再訪で必ず閉) / JSON-LD `genre`から除外 / `ThemeListPage`は別セクション / `ThemeDetailPage`は警告バナー / `HomePage`人気テーマから除外 / 関連作品レコメンドのスコア計算から除外

## データフロー(source → generated)

- `public/data/source/*.json` … 手作業で作成・**コミットする**一次データ(works/authors/translators/publishers/themes/awards)
- `public/data/generated/*.json` … `scripts/generate-manifest.mjs` がビルド時に生成する非正規化データ。**`.gitignore`対象**、`predev`/`prebuild`npmスクリプトで毎回再生成するので手で編集しない
- 生成スクリプトの検証(いずれも失敗するとビルドが落ちる):
  - 全Workの`authorIds`(空配列不可)/`translatorIds`/`publisherId`/`themeIds`/`awardResults[].awardId` の参照整合性
  - **`origin` の整合性**: `"overseas"` なら `translatorIds` が1件以上あり `originalTitle` があること / `"jp"` なら `translatorIds`・`originalTitle`・`jpPublishedYear` がいずれも空であること

## データモデル上の判断(mystery-dbから継承)

- **1作品(1タイトル)単位**で登録する(ranobe-dbのシリーズ単位と対照)。表紙取得がタイトル完全一致で効く
- **`firstPublishedYear` は原著の発表年**。海外作品も原書刊行年を入れることで、ウェルズ・クラークから現代作までをSF史の時系列で並べられる。邦訳初刊年は `jpPublishedYear` に分離(「本DBが採用した版の刊行年」の運用)
- **`seriesName` はエンティティ化しない**ただの表示用テキスト
- **`mediaMix` は `{ movie, drama, anime, comic }` の4種**をそのまま維持(SF小説は映像化・コミカライズが多い)
- 探偵エンティティは持たないため、`PersonKind`(author/translator/publisher)と汎用`PersonListPage`/`PersonDetailPage`だけで全人物系ページを賄う

## データ入力ルール(姉妹サイト共通)

- 出典は日本語版Wikipediaを基本とするが必須ではない(NDL・楽天書誌・出版社公式も可)。書き込む前に必ず裏取りし、`sourceNote`に何を確認したか・何が未確認かを明記
- **あらすじはコピペ禁止**。150〜250字で自分の言葉で要約(出版社紹介文の転記も禁止)。上記ネタバレ方針を守る
- **実在確認できない候補は無理に埋めない**
- 購入リンクは検索URL形式のみ、アフィリエイトタグ`izenmi-22`(姉妹サイト共通)。`amazonSearchUrl(title, 著者名)`
- 新規id追加前に既存JSONを確認して同一人物・同一賞の重複登録を避ける。人名は`scripts/find_people.py`で引く

## データ拡充時の作業フロー(mystery-dbの型を踏襲)

小バッチで作業し、バッチごとにコミット(pushは3バッチ程度まとめてでよい)。バッチ区切りで待機せず次バッチへ続行する。

1. 候補は`scripts/suggest_candidates.py`(楽天カタログ列挙)から取り、思いつきの書名は使わない
2. `scripts/probe_ndl.py`(NDLサーチ、内蔵DUP判定が先に走る)で書誌を裏取り。Wikipedia側は`scripts/probe.py`
3. `scripts/merge_batch.py`でprobe出力+annot JSONをbatch.jsonに合成 → `scripts/apply_batch.py`で反映(**applyは1回だけ**。リジェクト分は原因を直して小さなbatch.jsonで再投入)
4. `node scripts/generate-manifest.mjs`で整合性確認(フルビルドはCIに任せる)
5. `git add public/data/source && git commit`

mystery-dbで実証済みの注意: NDLの`first_year`は当てにならない(同名異作を巻き込む) / NDLは漫画版・児童書版・英語学習版を平然と返す(責任表示を見る) / あらすじへの非日本語断片混入を`re.search(r'[Ѐ-ӿ가-힯]')`等で点検 / 海外作品は`originalTitle`の重複集計で訳題違いの二重登録を検出できる。

## 受賞歴(awards)の方針

- scaffold時点で登録: 星雲賞(日本長編/海外長編等の部門は`result`で書き分け)、日本SF大賞、ハヤカワSFコンテスト、創元SF短編賞、日本SF新人賞、小松左京賞、ヒューゴー賞、ネビュラ賞、ローカス賞、アーサー・C・クラーク賞、フィリップ・K・ディック賞、「SFが読みたい!」年間ランキング
- 作品自体の受賞・順位だけを採用(候補・ノミネートは`sourceNote`に書くのみ)。映像版のみの受賞は対象外。著者の別作品受賞と本作受賞を区別。短編集は表題作単独の受賞を登録しない
- 受賞作の取り込みは**2段構え**(既存作品への受賞歴付与→未登録受賞作の追加)。Wikipediaの賞ページを正とする(`scripts/award_wiki.py`)

## テーマタグの方針

再利用可能な少数タグに絞る(1作品あたり4〜5個が目安)。新規タグ追加時は**spoilerフラグの要否を必ず判断**する。

## デザイン方針

- パステルカラー基調、グラデーションはなるべく使わない。**メインアクセントはコスミックブルー(`--color-cosmo` #8ea6f0 / `--color-cosmo-strong` #7189e6 / `--color-cosmo-deep` #6e8bff、色相約225°)**。ranobe-dbの水色(#7cd0ff、約200°)・mystery-dbの藤色(約255°)・tech-dbのティールと区別するための独自トリオで、装飾用パステル(pink/mint/yellow/peach/blue)のローテーションとは分けている
- `--color-primary`(リンク・ブランド用の紫)とアクセントは別変数
- ページ背景は黒一色固定。装飾(影・グラデーション・点線ボーダー等)は基本つけない
- 見出しは`M PLUS Rounded 1c`、favicon(`public/favicon.svg`)は黒地+「S」1文字(#6e8bff)。**四隅は不透明な黒**(mystery-db方式、角丸なし)。意匠を変えるときは`favicon.svg`と`scripts/generate-icons.mjs`の**両方**を直す

## コマンド

```sh
npm install
npm run dev       # http://localhost:5173/sf-db/
npm run build      # 型チェック + データ整合性チェック + ビルド + プリレンダー
npm run preview
npm run fetch-covers
node scripts/generate-ogp.mjs    # og-image.png再生成(手動、データ規模が変わったら)
node scripts/generate-icons.mjs  # favicon.ico/apple-touch-icon.png再生成(手動)
```

`main`へのpushで`.github/workflows/deploy.yml`が自動ビルド・GitHub Pagesデプロイ。`package.json`の`playwright`は`1.55.0`に**キャレット無しで固定**(このsandboxはNode 18のため。game-dbで確立した対策)。

## 表紙画像

`scripts/fetch-covers.mjs`はmystery-db版そのまま: 3段フォールバック(楽天ブックス → 楽天Kobo → BOOK☆WALKER)、**全経路で著者名一致必須**、検索キーワードは**邦題**。

- 楽天の認証情報は姉妹サイト共用(`RAKUTEN_APP_ID`/`RAKUTEN_ACCESS_KEY`、新gateway形式)。他サイトのfetch-coversと同時に走らせない(429)
- **楽天ブックスのジャンル除外`001017`(ライトノベル)は当面維持**。ハヤカワ文庫JA等のSF/ラノベ境界作品で正しい表紙が弾かれた場合は、除外を外すのではなく`covers-cache.json`をISBN直指定で個別に手当てし、`note`に理由を書く(恒久的に外すと同題ラノベ・ノベライズの誤マッチリスクが上がる)
- 海外古典は登録した版と別レーベルの書影になることがある(作品として同一なら採用可、`note`に食い違いを記録)。英語学習版・児童向け版・漫画版の誤マッチ類型はmystery-dbのCLAUDE.md参照。`matchedTitle`と実画像の目視確認は省略しない
- 未解決分の再挑戦は`--retry-misses`(`--force`は手動修正を上書きするので使わない)
- 実行は`run_in_background`で(10分のBashタイムアウト対策)

## SEO / SSG(mystery-dbから継承)

- `src/ui/common/useSeo.ts`: canonical/og:urlは固定の`SITE_ORIGIN`定数から組み立てる(prerender時にlocalhostが混入するのを防ぐ)
- JSON-LD: 作品詳細=`Book`、著者・翻訳者=`Person`、出版社=`Organization`、`BreadcrumbList`、トップ=`WebSite`+`SearchAction`
- `scripts/prerender.mjs`(npm `postbuild`): `const BASE = "/sf-db"`の直書きがある(vite.config.tsとは独立)
- 関連作品レコメンド: テーマタグのIDF重み付きコサイン類似度+著者共通ボーナス(+0.15)。spoilerタグはスコア計算から除外。同点はid昇順(ビルド決定性のため)
- **Google Analytics: `index.html`のGA4測定IDは`G-XXXXXXXXXX`のプレースホルダーのまま**。ユーザーがsf-db専用のGA4プロパティを発行したら差し替える(姉妹サイトのIDは流用禁止)。Search Consoleへのsitemap登録もユーザー操作が必要

## データ規模の推移

(初回scaffold: このセクションに件数を追記していく)
