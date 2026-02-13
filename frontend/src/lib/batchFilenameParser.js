const DATE_PATTERN = /(\d{4}-\d{2}-\d{2}|\d{8})/;
const TICKER_PATTERN = /^[A-Za-z]{1,10}$/;

const normalizeDate = (rawDate) => {
  if (!rawDate) return "";
  if (/^\d{4}-\d{2}-\d{2}$/.test(rawDate)) return rawDate;
  if (/^\d{8}$/.test(rawDate)) return `${rawDate.slice(0, 4)}-${rawDate.slice(4, 6)}-${rawDate.slice(6, 8)}`;
  return "";
};

const splitByDelimiters = (value, delimiters = ["_", "-", " "]) => {
  const escaped = delimiters.map((delimiter) => delimiter.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const delimiterPattern = new RegExp(`(?:${escaped.join("|")})+`);
  return value
    .split(delimiterPattern)
    .map((token) => token.trim())
    .filter(Boolean);
};

const pickBestTicker = (tokens) => {
  const candidates = tokens.filter((token) => TICKER_PATTERN.test(token));
  if (!candidates.length) return "";
  const uppercaseShort = candidates.find((token) => token === token.toUpperCase() && token.length <= 6);
  if (uppercaseShort) return uppercaseShort;
  const short = candidates.find((token) => token.length <= 6);
  return short || candidates[0];
};

const extractTickerNearDate = (stem, dateToken, delimiters) => {
  if (!dateToken) return "";
  const [before, after = ""] = stem.split(dateToken);
  const beforeTokens = splitByDelimiters(before, delimiters).reverse();
  const afterTokens = splitByDelimiters(after, delimiters);
  return pickBestTicker(beforeTokens) || pickBestTicker(afterTokens) || "";
};

export const parseBatchFilename = (filename, options = {}) => {
  const stem = String(filename || "").replace(/\.[^.]+$/, "");
  const delimiters = options.delimiters || ["_", "-", " "];

  if (!stem) {
    return { ticker: "", date: "", confidence: "none", requiresConfirmation: true, reason: "Filename is empty." };
  }

  const directTickerDate = stem.match(/^([A-Za-z]{1,10})[_\- ]+(\d{4}-\d{2}-\d{2}|\d{8})(?:[T_\- ].*)?$/);
  if (directTickerDate) {
    return {
      ticker: directTickerDate[1].toUpperCase(),
      date: normalizeDate(directTickerDate[2]),
      confidence: "high",
      requiresConfirmation: false,
      reason: "Matched TICKER_DATE format.",
    };
  }

  const directDateTicker = stem.match(/^(\d{4}-\d{2}-\d{2}|\d{8})[_\- ]+([A-Za-z]{1,10})(?:[_\- ].*)?$/);
  if (directDateTicker) {
    return {
      ticker: directDateTicker[2].toUpperCase(),
      date: normalizeDate(directDateTicker[1]),
      confidence: "high",
      requiresConfirmation: false,
      reason: "Matched DATE_TICKER format.",
    };
  }

  const dateToken = stem.match(DATE_PATTERN)?.[1] || "";
  const date = normalizeDate(dateToken);
  const tickerNearDate = extractTickerNearDate(stem, dateToken, delimiters);
  const tickerFallback = pickBestTicker(splitByDelimiters(stem, delimiters)) || "";
  const ticker = (tickerNearDate || tickerFallback).toUpperCase();

  if (ticker && date) {
    return {
      ticker,
      date,
      confidence: "medium",
      requiresConfirmation: true,
      reason: "Ticker/date detected heuristically. Confirm before upload.",
    };
  }

  return {
    ticker,
    date,
    confidence: "none",
    requiresConfirmation: true,
    reason: "Unable to confidently parse ticker/date.",
  };
};
