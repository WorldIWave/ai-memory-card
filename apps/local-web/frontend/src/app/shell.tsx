/**
 * Input: ?????????  |  Output: ?????????????
 * Output: ??????????????????
 * Role: ????????? app chrome ????
 * Use: ??????? router?????????????????
 */
import { BarChart2, BookOpen, Languages, Library, Settings } from "lucide-react";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet } from "react-router-dom";
import { cn } from "../lib/utils";

const navItems = [
  { to: "/", end: true as const, icon: BookOpen, key: "nav_review" },
  { to: "/library", end: false as const, icon: Library, key: "nav_library" },
  { to: "/evaluation", end: false as const, icon: BarChart2, key: "nav_data" },
  { to: "/settings", end: false as const, icon: Settings, key: "nav_profile" },
];

export function AppShell() {
  const { t, i18n } = useTranslation();

  function toggleLanguage() {
    const nextLanguage = i18n.language.startsWith("zh") ? "en" : "zh";
    void i18n.changeLanguage(nextLanguage);
    localStorage.setItem("lmca-lang", nextLanguage);
  }

  return (
    <div className="app-workspace">
      <aside className="app-sidebar" aria-label={t("app_title")}>
        <div className="app-brand">
          <span className="app-brand-mark" aria-hidden="true">
            L
          </span>
          <span className="app-brand-text">{t("app_title")}</span>
        </div>

        <nav className="app-nav-list" aria-label={t("app_title")}>
          {navItems.map(({ to, end, icon: Icon, key }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => cn("app-nav-item", isActive && "is-active")}
            >
              <Icon size={18} aria-hidden="true" />
              <span>{t(key)}</span>
            </NavLink>
          ))}
        </nav>

        <button
          type="button"
          className="app-language-button"
          aria-label={t("language_switch")}
          onClick={toggleLanguage}
        >
          <Languages size={18} aria-hidden="true" />
          <span>{i18n.language.startsWith("zh") ? "EN" : "中"}</span>
        </button>
      </aside>

      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
