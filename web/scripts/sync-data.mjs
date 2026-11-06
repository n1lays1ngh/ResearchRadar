// Copies the archived editions from ../data/editions into public/ so Vite (and Vercel's CDN)
// serve them as static files, and writes two small indexes:
//   public/data/editions.json   newest-first list of editions (for the archive and the front page)
//   public/data/papers.json     arXiv id -> edition date + section (so /paper/:id finds its report)
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const src = path.resolve(here, "../../data/editions");
const outEditions = path.resolve(here, "../public/editions");
const outData = path.resolve(here, "../public/data");

fs.rmSync(outEditions, { recursive: true, force: true });
fs.mkdirSync(outEditions, { recursive: true });
fs.mkdirSync(outData, { recursive: true });

const dates = fs.existsSync(src)
  ? fs.readdirSync(src).filter((f) => /^\d{4}-\d{2}-\d{2}\.json$/.test(f)).map((f) => f.slice(0, 10)).sort().reverse()
  : [];

const editions = [];
const papers = {};
for (const date of dates) {
  const ed = JSON.parse(fs.readFileSync(path.join(src, `${date}.json`), "utf8"));
  for (const ext of ["json", "pdf", "html"]) {
    const file = path.join(src, `${date}.${ext}`);
    if (fs.existsSync(file)) fs.copyFileSync(file, path.join(outEditions, `${date}.${ext}`));
  }
  editions.push({
    date,
    edition: ed.edition,
    issued: ed.issued,
    week_range: ed.week_range,
    scanned: ed.scanned,
    picked: ed.picked,
    pdf: fs.existsSync(path.join(src, `${date}.pdf`)),
    html: fs.existsSync(path.join(src, `${date}.html`)),
    sections: ed.sections.map((s) => ({ key: s.key, name: s.name })),
    leads: ed.sections.filter((s) => s.featured.length).map((s) => ({ section: s.key, id: s.featured[0].id, title: s.featured[0].title })),
  });
  for (const s of ed.sections) {
    for (const p of [...s.featured, ...s.more]) {
      if (!papers[p.id]) papers[p.id] = { date, section: s.key };   // newest edition wins
    }
  }
}
fs.writeFileSync(path.join(outData, "editions.json"), JSON.stringify(editions));
fs.writeFileSync(path.join(outData, "papers.json"), JSON.stringify(papers));
console.log(`[sync-data] ${editions.length} edition(s), ${Object.keys(papers).length} papers`);
