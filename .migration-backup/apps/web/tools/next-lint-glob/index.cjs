// Narrow compatibility boundary for @next/eslint-plugin-next 15.5.28 ONLY.
// Its sole fast-glob call is globSync(pattern, { onlyDirectories: true }).
const { isAbsolute } = require("node:path");
const { globSync: tinyGlobSync } = require("tinyglobby");
exports.globSync = function globSync(pattern, options) {
  if (typeof pattern !== "string" || options?.onlyDirectories !== true ||
      Object.keys(options).some((key) => key !== "onlyDirectories")) {
    throw new TypeError("Unsupported Next lint glob call; review compatibility adapter");
  }
  return tinyGlobSync(pattern, { onlyDirectories: true, absolute: isAbsolute(pattern) })
    .map((entry) => entry.length > 1 ? entry.replace(/\/$/, "") : entry);
};
