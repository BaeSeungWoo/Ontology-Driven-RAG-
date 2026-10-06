import type { ReactNode } from "react";
import Image from "next/image";
import Link from "next/link";
import PageTabs from "./pageTabs";
import styles from "./appHeader.module.css";

export default function AppHeader({ children }: { children?: ReactNode }) {
  return (
    <header className={styles.header}>
      <div className={styles.toolbarLeft}>
        <Link href="/chat" className={styles.brand} aria-label="Ontology-RAG 홈">
          <Image src="/logo3.png" alt="" width={80} height={80} loading="eager" className={styles.brandLogo} />
          <h1>Ontology-RAG</h1>
        </Link>
        <PageTabs />
      </div>
      {children}
    </header>
  );
}
