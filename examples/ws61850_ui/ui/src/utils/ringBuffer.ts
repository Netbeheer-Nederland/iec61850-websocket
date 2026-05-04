export function appendRingBuffer<T>(items: T[], next: T, max: number): T[] {
  if (items.length < max) return [...items, next];
  return [...items.slice(1), next];
}
