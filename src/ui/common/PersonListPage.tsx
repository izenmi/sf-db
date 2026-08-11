import type { PersonOrPublisherGenerated } from "../../types";
import { getAuthors, getTranslators, getPublishers } from "../../data/manifest";
import { useAsyncData } from "./useAsyncData";
import { Loading, ErrorState } from "./Status";
import { EntityList } from "./EntityList";
import { useSeo } from "./useSeo";

export type PersonKind = "author" | "translator" | "publisher";

const CONFIG: Record<
  PersonKind,
  { title: string; pathPrefix: string; fetcher: () => Promise<PersonOrPublisherGenerated[]>; descriptionNoun: string }
> = {
  author: { title: "著者一覧", pathPrefix: "/authors", fetcher: getAuthors, descriptionNoun: "著者" },
  translator: {
    title: "翻訳者一覧",
    pathPrefix: "/translators",
    fetcher: getTranslators,
    descriptionNoun: "翻訳者",
  },
  publisher: {
    title: "出版社一覧",
    pathPrefix: "/publishers",
    fetcher: getPublishers,
    descriptionNoun: "出版社",
  },
};

export function PersonListPage({ kind }: { kind: PersonKind }) {
  const { title, pathPrefix, fetcher, descriptionNoun } = CONFIG[kind];
  const state = useAsyncData(fetcher, [kind]);

  useSeo({
    title,
    description:
      state.status === "ready"
        ? `SF小説の${descriptionNoun}${state.data.length}件の一覧。五十音順に探せます。`
        : undefined,
  });

  return (
    <div className="page">
      <h1>{title}</h1>
      {state.status === "loading" && <Loading />}
      {state.status === "error" && <ErrorState error={state.error} />}
      {state.status === "ready" && (
        <>
          <p className="page-subtitle">{state.data.length}件</p>
          <EntityList items={state.data} pathPrefix={pathPrefix} />
        </>
      )}
    </div>
  );
}
