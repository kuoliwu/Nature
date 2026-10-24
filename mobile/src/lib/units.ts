/** 「A-1F-1, A-1F-2」或一行一戶 → 戶別清單（去除空白與重複） */
export function parseUnitList(text: string): string[] {
  const units = text
    .split(/[\r\n,，、;；\t]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  return [...new Set(units)];
}

export type UnitFormat = 'dash' | 'compact' | 'chinese';

export const UNIT_FORMATS: { key: UnitFormat; label: string; example: string }[] = [
  { key: 'dash', label: 'A-5F-1', example: 'A-5F-1' },
  { key: 'compact', label: 'A5-1', example: 'A5-1' },
  { key: 'chinese', label: 'A棟5樓之1', example: 'A棟5樓之1' },
];

export type GeneratedUnit = { unit_no: string; building: string; floor: string };

export type GenerateOptions = {
  letterFrom: string;
  letterTo: string;
  floorFrom: number;
  floorTo: number;
  perFloorFrom?: number | null; // 每層戶號（選填），例如 1～4
  perFloorTo?: number | null;
  format: UnitFormat;
};

export const MAX_GENERATED = 2000;

function unitNo(letter: string, floor: number, n: number | null, format: UnitFormat): string {
  switch (format) {
    case 'dash':
      return `${letter}-${floor}F${n === null ? '' : `-${n}`}`;
    case 'compact':
      return `${letter}${floor}${n === null ? '' : `-${n}`}`;
    case 'chinese':
      return `${letter}棟${floor}樓${n === null ? '' : `之${n}`}`;
  }
}

/** 棟別字母 × 樓層（× 每層戶號）排列組合產生戶別；輸入有誤時回傳錯誤訊息 */
export function generateUnits(o: GenerateOptions): { units: GeneratedUnit[] } | { error: string } {
  const from = o.letterFrom.trim().toUpperCase();
  const to = (o.letterTo.trim() || from).toUpperCase();
  if (!/^[A-Z]$/.test(from) || !/^[A-Z]$/.test(to)) return { error: '棟別請輸入單一英文字母，例如 A 到 C' };
  if (to < from) return { error: '棟別的結束字母不能在開始字母之前' };

  const ints = [o.floorFrom, o.floorTo];
  if (ints.some((n) => !Number.isInteger(n) || n < 1 || n > 99)) return { error: '樓層請輸入 1～99 的整數' };
  if (o.floorTo < o.floorFrom) return { error: '結束樓層不能小於開始樓層' };

  const hasPerFloor = o.perFloorFrom != null || o.perFloorTo != null;
  const pf = o.perFloorFrom ?? o.perFloorTo ?? 1;
  const pt = o.perFloorTo ?? o.perFloorFrom ?? 1;
  if (hasPerFloor && (![pf, pt].every((n) => Number.isInteger(n) && n >= 1 && n <= 50) || pt < pf)) {
    return { error: '每層戶號請輸入 1～50，且結束不能小於開始' };
  }

  const letters = Array.from({ length: to.charCodeAt(0) - from.charCodeAt(0) + 1 }, (_, i) =>
    String.fromCharCode(from.charCodeAt(0) + i),
  );
  const perFloor = hasPerFloor ? Array.from({ length: pt - pf + 1 }, (_, i) => pf + i) : [null];
  const total = letters.length * (o.floorTo - o.floorFrom + 1) * perFloor.length;
  if (total > MAX_GENERATED) return { error: `一次最多產生 ${MAX_GENERATED} 戶（目前 ${total} 戶）` };

  const units: GeneratedUnit[] = [];
  for (const letter of letters) {
    for (let floor = o.floorFrom; floor <= o.floorTo; floor++) {
      for (const n of perFloor) {
        units.push({ unit_no: unitNo(letter, floor, n, o.format), building: letter, floor: `${floor}F` });
      }
    }
  }
  return { units };
}
