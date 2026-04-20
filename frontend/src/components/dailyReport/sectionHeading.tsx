import styles from "./dailyReport.module.css";

type SectionHeadingProps = {
  idx: string;
  title: string;
  emphasize: string;
};

export default function SectionHeading({
  idx,
  title,
  emphasize,
}: SectionHeadingProps) {
  return (
    <div className={styles.sectionHeading}>
      <span className={styles.sectionIdx}>{idx}</span>
      <h2>
        {title} <em>{emphasize}</em>
      </h2>
      <span className={styles.sectionLine} />
    </div>
  );
}
