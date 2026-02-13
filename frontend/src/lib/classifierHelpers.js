export const shouldUploadByPolicy = (label, policy) => {
  if (label === "red") {
    return Boolean(policy.uploadRed);
  }
  if (label === "yellow") {
    return Boolean(policy.uploadYellow);
  }
  if (label === "none") {
    return !Boolean(policy.skipNone);
  }
  return false;
};

export const filterQueueByPolicy = (queue, policy) =>
  queue.filter((item) => !item.error && shouldUploadByPolicy(item.label, policy));

export const buildChecklistFieldsForLabel = (label) => ({
  red_candle: label === "red",
  yellow_candle: label === "yellow",
});
