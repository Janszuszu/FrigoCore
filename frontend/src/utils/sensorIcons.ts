/**
 * The sensor icon library.
 *
 * Each entry is a stable identifier (persisted in Sensor.icon), a Polish
 * label for the picker, and the SVG path data drawn on a 24x24 viewBox.
 * Identifiers must match the backend's slug rule: lowercase, digits and
 * hyphens, up to 32 characters.
 */

export interface SensorIconDef {
  label: string;
  paths: string[];
}

export const DEFAULT_SENSOR_ICON = "thermometer";

export const SENSOR_ICONS: Record<string, SensorIconDef> = {
  thermometer: {
    label: "Czujnik temperatury",
    paths: ["M10 14.2V4.5a2 2 0 0 1 4 0v9.7a4 4 0 1 1-4 0Z", "M12 7h2M12 10h2"],
  },
  evaporator: {
    label: "Parownik",
    paths: [
      "M3 6h18v12H3z",
      "M7 6v12M11 6v12M15 6v12",
      "M3 10h18M3 14h18",
    ],
  },
  condenser: {
    label: "Skraplacz",
    paths: [
      "M3 7h18v10H3z",
      "M6 10.5h12M6 13.5h12",
      "M12 3v4M8 3v4M16 3v4",
    ],
  },
  compressor: {
    label: "Sprężarka",
    paths: [
      "M4 9.5h9v9H4z",
      "M13 12h4a3 3 0 0 0 3-3V5",
      "M6.5 5.5h4",
      "M8.5 5.5v4",
    ],
  },
  snowflake: {
    label: "Mroźnia / śnieżynka",
    paths: [
      "M12 2v20M4.5 6.5l15 11M19.5 6.5l-15 11",
      "M12 6l-2.4-2.4M12 6l2.4-2.4M12 18l-2.4 2.4M12 18l2.4 2.4",
    ],
  },
  fan: {
    label: "Wentylator",
    paths: [
      "M12 12C10 9 9 5 12 2c3 3 2 7 0 10Z",
      "M12 12c3 0 7 1 8.7 4.5-3.5 1.7-6.9-.6-8.7-4.5Z",
      "M12 12c-1.8 3.9-5.2 6.2-8.7 4.5C5 13 9 12 12 12Z",
      "M12 12.9a.9.9 0 1 0 0-1.8.9.9 0 0 0 0 1.8Z",
    ],
  },
  room: {
    label: "Komora / pomieszczenie",
    paths: ["M4 11.5 12 4l8 7.5", "M6 10v9h12v-9", "M10.5 19v-4.5h3V19"],
  },
  outdoor: {
    label: "Temperatura zewnętrzna",
    paths: [
      "M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Z",
      "M12 2v2.5M12 19.5V22M4.2 4.2l1.8 1.8M18 18l1.8 1.8M2 12h2.5M19.5 12H22M4.2 19.8 6 18M18 6l1.8-1.8",
    ],
  },
  cabinet: {
    label: "Lada / regał chłodniczy",
    paths: ["M4 3h16v18H4z", "M4 12h16", "M14 7.5h3M14 16.5h3"],
  },
  pipe: {
    label: "Rurociąg / tłoczenie",
    paths: [
      "M3 8h7a4 4 0 0 1 4 4v0a4 4 0 0 0 4 4h3",
      "M3 5.5v5M21 13.5v5",
    ],
  },
  pressure: {
    label: "Ciśnienie",
    paths: [
      "M12 3a9 9 0 0 0-9 9 9 9 0 0 0 1.6 5.1h14.8A9 9 0 0 0 21 12a9 9 0 0 0-9-9Z",
      "M12 12l4.5-3.5",
    ],
  },
  door: {
    label: "Drzwi komory",
    paths: ["M6 3h12v18H6z", "M14.5 12.5v1.2"],
  },
  power: {
    label: "Zasilanie / agregat",
    paths: ["M13 2 4 14h7l-1 8 9-12h-7l1-8Z"],
  },
  humidity: {
    label: "Wilgotność",
    paths: ["M12 3.5c3.4 4 6 6.9 6 9.9a6 6 0 0 1-12 0c0-3 2.6-5.9 6-9.9Z"],
  },
};

export const SENSOR_ICON_IDS = Object.keys(SENSOR_ICONS);

/**
 * Best-guess icon for a sensor that has never been configured, derived from
 * its name. Only used as a suggestion in the picker — what is stored is
 * always the administrator's explicit choice.
 */
export function suggestIconFromName(name: string): string {
  const n = name
    .toLowerCase()
    .replaceAll("ł", "l")
    .replaceAll("ą", "a")
    .replaceAll("ę", "e")
    .replaceAll("ó", "o")
    .replaceAll("ś", "s")
    .replaceAll("ż", "z")
    .replaceAll("ź", "z")
    .replaceAll("ć", "c")
    .replaceAll("ń", "n");
  if (n.includes("skraplacz")) return "condenser";
  if (n.includes("parownik")) return "evaporator";
  if (n.includes("spreza") || n.includes("kompresor")) return "compressor";
  if (n.includes("tlocz") || n.includes("rura")) return "pipe";
  if (n.includes("wentylator")) return "fan";
  if (n.includes("lada") || n.includes("regal")) return "cabinet";
  if (n.includes("mroz")) return "snowflake";
  if (n.includes("komora") || n.includes("chlodni") || n.includes("pomieszcz"))
    return "room";
  if (
    n.includes("zewnetrz") ||
    n.includes("otoczeni") ||
    n.includes("ambient") ||
    n.includes("outdoor")
  )
    return "outdoor";
  if (n.includes("cisnien")) return "pressure";
  if (n.includes("drzwi")) return "door";
  if (n.includes("wilgot")) return "humidity";
  if (n.includes("agregat") || n.includes("zasilan")) return "power";
  return DEFAULT_SENSOR_ICON;
}
