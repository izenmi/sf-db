import { getThemes } from "../../data/manifest";
import { useAsyncData } from "../common/useAsyncData";
import { Loading, ErrorState } from "../common/Status";
import { EntityList } from "../common/EntityList";
import { useSeo } from "../common/useSeo";

/** Spoiler tags are split into their own section rather than hidden: a tag name on its own
 *  ("叙述トリック") gives nothing away — it's the pairing with a specific work that spoils, and
 *  that only happens once the reader clicks through. */
export function ThemeListPage() {
  const state = useAsyncData(getThemes, []);

  useSeo({
    title: "テーマ一覧",
    description:
      state.status === "ready"
        ? `${state.data.length}種類のテーマ・サブジャンルからSF小説を探せます。`
        : undefined,
  });

  const openThemes = state.status === "ready" ? state.data.filter((t) => !t.spoiler) : [];
  const spoilerThemes = state.status === "ready" ? state.data.filter((t) => t.spoiler) : [];

  return (
    <div className="page">
      <h1>テーマ</h1>
      {state.status === "loading" && <Loading />}
      {state.status === "error" && <ErrorState error={state.error} />}
      {state.status === "ready" && (
        <>
          <p className="page-subtitle">{state.data.length}件</p>
          <EntityList items={openThemes} pathPrefix="/themes" />
          {spoilerThemes.length > 0 && (
            <>
              <h2 className="home-section__heading font-display">ネタバレを含むタグ</h2>
              <p className="spoiler-block__note">
                以下のタグは、作品に付いていること自体が真相の手がかりになります。未読作品のネタバレを避けたい場合は開かないでください。
              </p>
              <EntityList items={spoilerThemes} pathPrefix="/themes" />
            </>
          )}
        </>
      )}
    </div>
  );
}
