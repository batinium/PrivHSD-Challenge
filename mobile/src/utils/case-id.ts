const HASH_OFFSET = 0x811c9dc5;
const HASH_PRIME = 0x01000193;

export function makePublicCaseId(source: string, protectedText: string) {
  let hash = HASH_OFFSET;
  const input = `${source}\n${protectedText}`;

  for (let index = 0; index < input.length; index += 1) {
    hash ^= input.charCodeAt(index);
    hash = Math.imul(hash, HASH_PRIME);
  }

  return `case-${(hash >>> 0).toString(16).padStart(8, '0')}`;
}
