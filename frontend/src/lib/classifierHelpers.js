export const shouldUploadByPolicy = (label, policy) => {
  if (label === "red") {
    return Boolean(policy.uploadRed);
  }
  if (label === "yellow") {
    return Boolean(policy.uploadYellow);
  }
  if (label === "none") {
    return Boolean(policy.uploadNone);
  }
  return false;
};

export const policyToApiPayload = (policy) => ({
  policy_red: policy.uploadRed ? "upload" : "skip",
  policy_yellow: policy.uploadYellow ? "upload" : "skip",
  policy_none: policy.uploadNone ? "upload" : "skip",
});

export const filterQueueByPolicy = (queue, policy) =>
  queue.filter((item) => !item.error && shouldUploadByPolicy(item.label, policy));

export const buildChecklistFieldsForLabel = (label) => ({
  red_candle: label === "red",
  yellow_candle: label === "yellow",
});

export const rowSkipReason = (item, policy) => {
  if (item.error) {
    return item.error;
  }
  if (!shouldUploadByPolicy(item.label, policy)) {
    return "Skipped by policy.";
  }
  if (!item.ticker || !item.date) {
    return "Missing ticker/date metadata.";
  }
  if (item.requiresConfirmation && !item.isConfirmed) {
    return "Metadata confirmation required.";
  }
  return "Eligible for upload.";
};
