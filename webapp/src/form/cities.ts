// German cities with 100 000+ inhabitants (Großstädte) and their Land code (codes as in app/data/regions.py).
// Hand-written list of well-known facts; any other place can still be typed, then the Land is asked.
export const CITIES: [string, string][] = [
  ["Berlin", "BE"], ["Hamburg", "HH"], ["München", "BY"], ["Köln", "NW"], ["Frankfurt am Main", "HE"], ["Stuttgart", "BW"],
  ["Düsseldorf", "NW"], ["Leipzig", "SN"], ["Dortmund", "NW"], ["Essen", "NW"], ["Bremen", "HB"], ["Dresden", "SN"],
  ["Hannover", "NI"], ["Nürnberg", "BY"], ["Duisburg", "NW"], ["Bochum", "NW"], ["Wuppertal", "NW"], ["Bielefeld", "NW"],
  ["Bonn", "NW"], ["Münster", "NW"], ["Mannheim", "BW"], ["Karlsruhe", "BW"], ["Augsburg", "BY"], ["Wiesbaden", "HE"],
  ["Mönchengladbach", "NW"], ["Gelsenkirchen", "NW"], ["Aachen", "NW"], ["Braunschweig", "NI"], ["Kiel", "SH"],
  ["Chemnitz", "SN"], ["Halle (Saale)", "ST"], ["Magdeburg", "ST"], ["Freiburg im Breisgau", "BW"], ["Krefeld", "NW"],
  ["Mainz", "RP"], ["Lübeck", "SH"], ["Erfurt", "TH"], ["Oberhausen", "NW"], ["Rostock", "MV"], ["Kassel", "HE"],
  ["Hagen", "NW"], ["Potsdam", "BB"], ["Saarbrücken", "SL"], ["Hamm", "NW"], ["Ludwigshafen am Rhein", "RP"],
  ["Mülheim an der Ruhr", "NW"], ["Oldenburg", "NI"], ["Osnabrück", "NI"], ["Leverkusen", "NW"], ["Heidelberg", "BW"],
  ["Darmstadt", "HE"], ["Solingen", "NW"], ["Regensburg", "BY"], ["Herne", "NW"], ["Paderborn", "NW"], ["Neuss", "NW"],
  ["Ingolstadt", "BY"], ["Offenbach am Main", "HE"], ["Fürth", "BY"], ["Würzburg", "BY"], ["Ulm", "BW"], ["Heilbronn", "BW"],
  ["Pforzheim", "BW"], ["Wolfsburg", "NI"], ["Göttingen", "NI"], ["Bottrop", "NW"], ["Reutlingen", "BW"], ["Koblenz", "RP"],
  ["Bremerhaven", "HB"], ["Recklinghausen", "NW"], ["Erlangen", "BY"], ["Bergisch Gladbach", "NW"], ["Remscheid", "NW"],
  ["Jena", "TH"], ["Trier", "RP"], ["Salzgitter", "NI"], ["Moers", "NW"], ["Siegen", "NW"], ["Hildesheim", "NI"],
  ["Cottbus", "BB"], ["Gütersloh", "NW"], ["Kaiserslautern", "RP"], ["Schwerin", "MV"], ["Witten", "NW"],
];

/** Case- and umlaut-insensitive prefix match ( "munchen" and "muenchen" find München). */
const fold = (s: string) => s.toLowerCase().replace(/ä/g, "a").replace(/ö/g, "o").replace(/ü/g, "u").replace(/ß/g, "ss")
  .replace(/ae/g, "a").replace(/oe/g, "o").replace(/ue/g, "u");
export function findCities(q: string, limit = 5): [string, string][] {
  const f = fold(q.trim());
  if (f.length < 2) return [];
  const starts = CITIES.filter(([c]) => fold(c).startsWith(f));
  const inside = CITIES.filter(([c]) => !fold(c).startsWith(f) && fold(c).includes(f));
  return [...starts, ...inside].slice(0, limit);
}
export const landOf = (city: string) => CITIES.find(([c]) => c === city)?.[1] ?? null;

export const LANDS: Record<string, string> = {
  BW: "Baden-Württemberg", BY: "Bayern", BE: "Berlin", BB: "Brandenburg", HB: "Bremen", HH: "Hamburg", HE: "Hessen",
  MV: "Mecklenburg-Vorpommern", NI: "Niedersachsen", NW: "Nordrhein-Westfalen", RP: "Rheinland-Pfalz", SL: "Saarland",
  SN: "Sachsen", ST: "Sachsen-Anhalt", SH: "Schleswig-Holstein", TH: "Thüringen",
};
