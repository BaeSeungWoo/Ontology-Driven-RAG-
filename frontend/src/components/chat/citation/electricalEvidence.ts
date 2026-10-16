/** Use the selected chunk's claims, excluding the list of all reviewed sheets. */
export function electricalClaimText(answer: string, chunkIndex: number): string {
  const body = answer.split(/\n\s*검토한 도면 페이지\s*:/)[0];
  return body.split(/\r?\n/).filter(line => {
    return [...line.matchAll(/\[chunk:(\d+)\]/gi)].some(match => Number(match[1]) === chunkIndex);
  }).map(line => line.replace(/^>\s?/, "").replace(/\*\*([^*\n]+)\*\*/g, "$1").replace(/\[chunk:\d+\]/gi, "").trim()).join("\n");
}
