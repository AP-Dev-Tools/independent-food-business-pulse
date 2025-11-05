// scripts/make-top10.js
// Usage: node scripts/make-top10.js <path-to-xml-root>
// Reads last run's businesses from data/businesses_latest.json (if present),
// parses today's XMLs, then writes:
//   data/businesses_previous.json
//   data/businesses_latest.json
//   data/la_deltas_latest.json

import fs from "fs";
import path from "path";
import { XMLParser } from "fast-xml-parser";

const SECTORS = {
  MOBILE: "Mobile caterer",
  RESTAURANT_CAFE: "Restaurant/Cafe/Canteen",
  PUB_BAR: "Pub/bar/nightclub",
  TAKEAWAY: "Takeaway/sandwich shop",
};

const MONITORED = new Set(Object.values(SECTORS));

function readJSONSafe(p, fallback) {
  try {
    return JSON.parse(fs.readFileSync(p, "utf8"));
  } catch {
    return fallback;
  }
}

function* walk(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const e of entries) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) yield* walk(p);
    else if (e.isFile() && p.toLowerCase().endsWith(".xml")) yield p;
  }
}

function parseCurrentBusinesses(xmlRoot) {
  const parser = new XMLParser({ ignoreAttributes: false, trimValues: true });
  const out = [];
  for (const file of walk(xmlRoot)) {
    const xml = fs.readFileSync(file, "utf8");
    const doc = parser.parse(xml);

    // Handle both single and array structures robustly
    const list =
      doc?.FHRSEstablishment?.EstablishmentCollection
        ?.EstablishmentDetail || [];

    const items = Array.isArray(list) ? list : [list];
    for (const est of items) {
      const type = est?.BusinessType || "";
      if (!MONITORED.has(type)) continue;

      out.push({
        id: est?.FHRSID ?? "",
        la: est?.LocalAuthorityName ?? "",
        type,
      });
    }
  }
  return out;
}

function byLA(items, wantedType) {
  const m = new Map();
  for (const e of items) {
    if (e.type !== wantedType) continue;
    const la = e.la || "Unknown";
    m.set(la, (m.get(la) || 0) + 1);
  }
  return m;
}

function top10(prev, curr, wantedType) {
  const p = byLA(prev, wantedType);
  const c = byLA(curr, wantedType);
  const las = new Set([...p.keys(), ...c.keys()]);
  const rows = [...las].map((la) => ({
    la,
    delta: (c.get(la) || 0) - (p.get(la) || 0),
    current: c.get(la) || 0,
  }));
  return {
    growth: rows.filter((r) => r.delta > 0).sort((a, b) => b.delta - a.delta).slice(0, 10),
    reductions: rows.filter((r) => r.delta < 0).sort((a, b) => a.delta - b.delta).slice(0, 10),
  };
}

async function main() {
  const xmlRoot = process.argv[2] || "work/xml"; // <-- change if your XMLs land elsewhere
  if (!fs.existsSync(xmlRoot)) {
    console.error(`XML folder not found: ${xmlRoot}`);
    process.exit(1);
  }

  fs.mkdirSync("data", { recursive: true });

  // previous = last committed latest (if present)
  const prev = readJSONSafe("data/businesses_latest.json", []);

  // current = parse XMLs now
  const curr = parseCurrentBusinesses(xmlRoot);

  // write previous + latest snapshots of businesses
  fs.writeFileSync("data/businesses_previous.json", JSON.stringify(prev, null, 2));
  fs.writeFileSync("data/businesses_latest.json", JSON.stringify(curr, null, 2));

  // build by_sector payload
  const by_sector = {};
  for (const [key, label] of Object.entries(SECTORS)) {
    by_sector[key] = top10(prev, curr, label);
  }

  // pick a date: use latest_snapshot.json if present, else today
  let date = new Date().toISOString().slice(0, 10);
  const latestSnap = readJSONSafe("data/latest_snapshot.json", null);
  if (latestSnap?.date) date = latestSnap.date;

  fs.writeFileSync(
    "data/la_deltas_latest.json",
    JSON.stringify({ date, by_sector }, null, 2)
  );

  console.log("✅ Wrote data/la_deltas_latest.json (Top-10), plus businesses_previous/latest.");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
