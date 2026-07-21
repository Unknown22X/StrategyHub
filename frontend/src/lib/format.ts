const arabicLatinDigitsLocale = "ar-SA-u-nu-latn";
const nonLatinDigitPattern = /[\u0660-\u0669\u06f0-\u06f9]/g;

const numberFormatter = new Intl.NumberFormat(arabicLatinDigitsLocale, {
  numberingSystem: "latn",
  maximumFractionDigits: 8,
});

const compactFormatter = new Intl.NumberFormat(arabicLatinDigitsLocale, {
  numberingSystem: "latn",
  notation: "compact",
  maximumFractionDigits: 2,
});

const dateTimeFormatter = new Intl.DateTimeFormat(arabicLatinDigitsLocale, {
  numberingSystem: "latn",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  day: "2-digit",
  month: "short",
});

export function toEnglishDigits(value: string): string {
  return value.replace(nonLatinDigitPattern, (digit) => {
    const codePoint = digit.codePointAt(0);
    if (codePoint === undefined) return digit;
    if (codePoint >= 0x0660 && codePoint <= 0x0669) {
      return String(codePoint - 0x0660);
    }
    if (codePoint >= 0x06f0 && codePoint <= 0x06f9) {
      return String(codePoint - 0x06f0);
    }
    return digit;
  });
}

export function formatDecimal(
  value: string | number | null | undefined,
  fallback = "غير متاح",
): string {
  if (value === null || value === undefined || value === "") {
    return fallback;
  }
  const numeric = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numeric)
    ? toEnglishDigits(numberFormatter.format(numeric))
    : fallback;
}

export function formatMoney(
  value: string | number | null | undefined,
  currency = "USDT",
): string {
  const formatted = formatDecimal(value);
  return formatted === "غير متاح" ? formatted : `${formatted} ${currency}`;
}

export function formatPercent(
  value: string | number | null | undefined,
): string {
  const formatted = formatDecimal(value);
  return formatted === "غير متاح" ? formatted : `${formatted}٪`;
}

export function formatCompact(
  value: string | number | null | undefined,
): string {
  if (value === null || value === undefined || value === "") {
    return "غير متاح";
  }
  const numeric = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numeric)
    ? toEnglishDigits(compactFormatter.format(numeric))
    : "غير متاح";
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "غير متاح";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "غير متاح"
    : toEnglishDigits(dateTimeFormatter.format(date));
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || seconds < 0) {
    return "غير متاح";
  }
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours > 0) {
    const formattedHours = toEnglishDigits(numberFormatter.format(hours));
    const formattedMinutes = toEnglishDigits(numberFormatter.format(minutes));
    return `${formattedHours} س ${formattedMinutes} د`;
  }
  return `${toEnglishDigits(numberFormatter.format(minutes))} دقيقة`;
}

export function directionLabel(direction: string | null | undefined): string {
  const labels: Record<string, string> = {
    long: "شراء",
    short: "بيع",
    both: "شراء وبيع",
  };
  return direction ? (labels[direction] ?? direction) : "غير متاح";
}

export function strategyStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    running: "يعمل تلقائياً",
    monitoring: "مراقبة",
    paused: "متوقف مؤقتاً",
    stopped: "متوقف",
    error: "خطأ",
  };
  return labels[status] ?? status;
}
