export type GuardResult = {
  text: string;
  findings: string[];
};

const DIRECT_IDENTIFIER_PATTERNS: [string, RegExp, string][] = [
  ['email', /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, '[EMAIL]'],
  ['url', /https?:\/\/[^\s]+/gi, '[URL]'],
  ['phone', /\+?\d[\d .()/-]{7,}\d/g, '[PHONE]'],
  ['social_handle', /@[A-Za-z0-9._-]{3,}/g, '[USER]'],
  ['ip_address', /\b(?:\d{1,3}\.){3}\d{1,3}\b/g, '[IP_ADDRESS]'],
];

const PLACEHOLDER_PATTERN = /\[[A-Z][A-Z_]*(?::[A-Za-z0-9_/-]+)?\]/g;

export function guardRestatement(restatement: string): GuardResult {
  let text = restatement;
  const findings: string[] = [];

  for (const [name, pattern, replacement] of DIRECT_IDENTIFIER_PATTERNS) {
    if (pattern.test(text)) {
      findings.push(name);
      text = text.replace(pattern, replacement);
    }
  }

  const placeholders = new Set(text.match(PLACEHOLDER_PATTERN) ?? []);
  for (const placeholder of placeholders) {
    findings.push(`placeholder:${placeholder}`);
  }

  return {
    text,
    findings: Array.from(new Set(findings)),
  };
}

export function summarizeGuard(findings: string[]): string {
  if (findings.length === 0) {
    return 'No direct identifier leakage detected';
  }
  return `${findings.length} guard finding${findings.length === 1 ? '' : 's'}`;
}
