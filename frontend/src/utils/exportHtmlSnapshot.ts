function escapeAttribute(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/"/g, "&quot;");
}

function escapeText(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function buildHtmlSnapshot(element: HTMLElement, title: string, printStyles = "") {
  const snapshot = element.cloneNode(true) as HTMLElement;
  snapshot.querySelectorAll("[data-export-control]").forEach((control) => control.remove());
  const css = Array.from(document.styleSheets)
    .map((styleSheet) => {
      try {
        return Array.from(styleSheet.cssRules).map((rule) => rule.cssText).join("\n");
      } catch {
        return "";
      }
    })
    .join("\n");
  const html = `<!doctype html>
<html lang="ko" class="${escapeAttribute(document.documentElement.className)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${escapeText(title)}</title>
  <style>${css}</style>
  <style>body{margin:0;padding:24px;background:#f4f7fb}.mes-export-page{max-width:1280px;margin:0 auto}</style>
  ${printStyles ? `<style>${printStyles}</style>` : ""}
</head>
<body class="${escapeAttribute(document.body.className)}">
  <main class="mes-export-page">${snapshot.outerHTML}</main>
</body>
</html>`;
  return html;
}

export function exportHtmlSnapshot(element: HTMLElement, title: string, fileName: string) {
  const html = buildHtmlSnapshot(element, title);
  const url = URL.createObjectURL(new Blob([html], { type: "text/html;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function printHtmlSnapshot(element: HTMLElement, title: string) {
  const printStyles = `
@page{size:A4 portrait;margin:10mm}
@media print{
  html,body{background:#fff!important}
  body{padding:0!important;-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .mes-export-page{max-width:none!important}
  [class*="executiveReport"]{box-shadow:none!important}
  [class*="executiveHeader"]{padding:18px!important}
  [class*="reportSections"]{grid-template-columns:minmax(0,1fr)!important;gap:12px!important;padding:16px!important}
  [class*="reportSectionWide"],[class*="overviewMetrics"]{grid-column:auto!important}
  [class*="overviewMetrics"],[class*="sevenDayForecastGrid"]{grid-template-columns:repeat(2,minmax(0,1fr))!important}
  [class*="issueGrid"],[class*="actionGrid"],[class*="salesContent"],[class*="performanceContent"],[class*="deliveryRiskContent"]{grid-template-columns:minmax(0,1fr)!important}
  [class*="deliveryRiskOrdersTable"]{min-width:0!important;font-size:8px!important}
  [class*="deliveryRiskOrdersTable"] th,[class*="deliveryRiskOrdersTable"] td{padding-right:4px!important;padding-left:4px!important}
  section[class*="reportSection"]:not([class*="reportSections"]){break-inside:auto!important}
  h2,h3,h4,thead{break-after:avoid}
  thead{display:table-header-group}
  article,tr{break-inside:avoid}
}`;
  const printWindow = window.open("", "_blank");
  if (!printWindow) {
    window.alert("PDF 내보내기 창을 열 수 없습니다. 브라우저의 팝업 차단을 해제해 주세요.");
    return;
  }

  const openPrintDialog = async () => {
    await printWindow.document.fonts?.ready;
    await new Promise<void>((resolve) => {
      printWindow.requestAnimationFrame(() => printWindow.requestAnimationFrame(() => resolve()));
    });
    if (printWindow.closed) return;
    printWindow.focus();
    printWindow.print();
  };

  printWindow.addEventListener("afterprint", () => printWindow.close(), { once: true });
  printWindow.document.write(buildHtmlSnapshot(element, title, printStyles));
  printWindow.document.close();
  if (printWindow.document.readyState === "complete") {
    void openPrintDialog();
  } else {
    printWindow.addEventListener("load", () => void openPrintDialog(), { once: true });
  }
}
