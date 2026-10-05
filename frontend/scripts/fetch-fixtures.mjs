// Authoring tool only: the website never calls source providers directly.
import { mkdir, writeFile } from "node:fs/promises";
const out = new URL("../src/mocks/fixtures/", import.meta.url);
await mkdir(out, { recursive: true });
for (const lang of ["ar", "en", "ur"]) {
  const url = `https://hadeethenc.com/api/v1/hadeeths/one/?language=${lang}&id=6267`;
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Source failed: ${response.status}`);
  const data = await response.json();
  await writeFile(
    new URL(`hadith-${lang}.json`, out),
    JSON.stringify(
      {
        id: data.id,
        title: data.title,
        attribution: data.attribution,
        grade: data.grade,
        url: `https://hadeethenc.com/${lang}/browse/hadith/6267`,
        fetched_from: url,
        fetched_at: new Date().toISOString(),
      },
      null,
      2,
    ) + "\n",
  );
}
const url = "https://quranenc.com/api/v1/translation/aya/english_saheeh/94/5";
const response = await fetch(url);
if (!response.ok) throw new Error(`Source failed: ${response.status}`);
const data = await response.json();
await writeFile(
  new URL("quran.json", out),
  JSON.stringify(
    {
      ...data.result,
      url: "https://quranenc.com/en/browse/english_saheeh/94#5",
      fetched_from: url,
      fetched_at: new Date().toISOString(),
    },
    null,
    2,
  ) + "\n",
);
