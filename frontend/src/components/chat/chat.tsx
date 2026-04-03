import Answer from "./answer/answer";
import Citation from "./citation/citation";
import History from "./history/history";
import PromptSetting from "./promptSetting/promptSetting";
import Question from "./question/question";
import ThemeSwitcher, { type ThemeKey } from "./themeSwitcher/themeSwitcher";
import styles from "./chat.module.css";

export default function Chat() {
  const themeKey =
    (process.env.NEXT_PUBLIC_FACTORY_THEME as ThemeKey) || "default";

  return (
    <div className={styles.chatPage}>

      {/* 공장별 테마 테스트용 버튼 스위처 */}
      <div className={styles.chatToolbar}>
        <ThemeSwitcher initialTheme={themeKey} />
      </div>

      <div className={styles.chatLayout}>
        <aside className={styles.chatLeft}>
          <section className={styles.chatCitationPane}>
            <Citation />
          </section>
        </aside>

        <main className={styles.chatCenter}>
          <section className={styles.chatAnswerPane}>
            <Answer />
          </section>
          <section className={styles.chatQuestionPane}>
            <Question />
          </section>
        </main>

        <aside className={styles.chatRight}>
          <section className={styles.chatHistoryPane}>
            <History />
          </section>
          <section className={styles.chatPromptSettingPane}>
            <PromptSetting />
          </section>
        </aside>
      </div>
    </div>
  );
}
