import api from "@/services/api";

function escapeAttribute(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/"/g, "&quot;");
}

function escapeText(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function buildHtmlSnapshot(element: HTMLElement, title: string, printStyles = "") {
  const snapshot = element.cloneNode(true) as HTMLElement;
  // The exported subtree loses theme variables and typography inherited from the page.
  const computed = window.getComputedStyle(element);
  for (const property of Array.from(computed)) {
    if (property.startsWith("--")) snapshot.style.setProperty(property, computed.getPropertyValue(property));
  }
  for (const property of ["font-family", "color"]) {
    snapshot.style.setProperty(property, computed.getPropertyValue(property));
  }
  // CSSOM can lose variable-based border shorthands when one side is overridden.
  const originals = [element, ...element.querySelectorAll<HTMLElement | SVGElement>("*")];
  const copies = [snapshot, ...snapshot.querySelectorAll<HTMLElement | SVGElement>("*")];
  originals.forEach((original, index) => {
    const style = window.getComputedStyle(original);
    for (const side of ["top", "right", "bottom", "left"]) {
      if (parseFloat(style.getPropertyValue(`border-${side}-width`)) > 0) {
        for (const part of ["width", "style", "color"]) {
          const property = `border-${side}-${part}`;
          copies[index].style.setProperty(property, style.getPropertyValue(property));
        }
      }
    }
  });
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

export async function exportPdfSnapshot(
  element: HTMLElement,
  title: string,
  fileName: string,
) {
  const response = await api.post<Blob>(
    "/api/mes/export-pdf",
    { html: buildHtmlSnapshot(element, title) },
    { responseType: "blob" },
  );
  const url = URL.createObjectURL(response.data);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
