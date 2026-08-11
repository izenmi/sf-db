import { BrowserRouter, Route, Routes } from "react-router-dom";
import { TopNav } from "./ui/common/TopNav";
import { ScrollToTop } from "./ui/common/ScrollToTop";
import { HomePage } from "./ui/home/HomePage";
import { WorkListPage } from "./ui/works/WorkListPage";
import { WorkDetailPage } from "./ui/works/WorkDetailPage";
import { ThemeListPage } from "./ui/themes/ThemeListPage";
import { ThemeDetailPage } from "./ui/themes/ThemeDetailPage";
import { PersonListPage } from "./ui/common/PersonListPage";
import { PersonDetailPage } from "./ui/common/PersonDetailPage";
import { AwardListPage } from "./ui/awards/AwardListPage";
import { AwardDetailPage } from "./ui/awards/AwardDetailPage";
import { AboutPage } from "./ui/about/AboutPage";
import { NotFoundPage } from "./ui/common/NotFoundPage";
import { AffiliateNotice } from "./ui/common/AffiliateNotice";

export function App() {
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <ScrollToTop />
      <TopNav />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/works" element={<WorkListPage />} />
        <Route path="/works/:id" element={<WorkDetailPage />} />
        <Route path="/themes" element={<ThemeListPage />} />
        <Route path="/themes/:id" element={<ThemeDetailPage />} />
        <Route path="/authors" element={<PersonListPage kind="author" />} />
        <Route path="/authors/:id" element={<PersonDetailPage kind="author" />} />
        <Route path="/translators" element={<PersonListPage kind="translator" />} />
        <Route path="/translators/:id" element={<PersonDetailPage kind="translator" />} />
        <Route path="/publishers" element={<PersonListPage kind="publisher" />} />
        <Route path="/publishers/:id" element={<PersonDetailPage kind="publisher" />} />
        <Route path="/awards" element={<AwardListPage />} />
        <Route path="/awards/:id" element={<AwardDetailPage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
      <AffiliateNotice />
    </BrowserRouter>
  );
}
