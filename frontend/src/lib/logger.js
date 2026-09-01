const isProd = process.env.NODE_ENV === "production";

function shouldLog() {
  if (typeof window !== "undefined" && window.__SNP_ENABLE_LOGS__) return true;
  return !isProd;
}

export const logger = {
  warn: (...args) => {
    if (shouldLog()) {
      console.warn(...args);
    }
  },
  log: (...args) => {
    if (shouldLog()) {
      console.log(...args);
    }
  },
  error: (...args) => {
    if (shouldLog()) {
      console.error(...args);
    }
  },
  debug: (...args) => {
    if (shouldLog()) {
      console.debug(...args);
    }
  },
};

export default logger;
