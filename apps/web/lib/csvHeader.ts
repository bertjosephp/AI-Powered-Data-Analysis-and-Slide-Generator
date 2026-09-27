/**
 * Column names from a CSV's header row, read in the browser so the user can pick
 * the outcome column before uploading. Returns null for non-CSV files (Excel
 * headers need a parser; those users type the column name instead).
 */
export async function readCsvHeader(file: File): Promise<string[] | null> {
  if (!file.name.toLowerCase().endsWith(".csv")) return null;
  const head = await readText(file.slice(0, 64 * 1024));
  const line = head.replace(/^\uFEFF/, "").split(/\r?\n/, 1)[0] ?? "";
  if (!line.trim()) return null;
  const delimiter = [",", ";", "\t", "|"].reduce((best, d) =>
    count(line, d) > count(line, best) ? d : best,
  );
  return splitRow(line, delimiter)
    .map((c) => c.trim())
    .filter(Boolean);
}

function readText(blob: Blob): Promise<string> {
  if (typeof blob.text === "function") return blob.text();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
}

function count(text: string, ch: string): number {
  return text.split(ch).length - 1;
}

function splitRow(line: string, delimiter: string): string[] {
  const cells: string[] = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (quoted && line[i + 1] === '"') {
        cell += '"';
        i++;
      } else {
        quoted = !quoted;
      }
    } else if (ch === delimiter && !quoted) {
      cells.push(cell);
      cell = "";
    } else {
      cell += ch;
    }
  }
  cells.push(cell);
  return cells;
}
