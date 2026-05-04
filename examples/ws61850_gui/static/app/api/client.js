export async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    const message = data && typeof data.error === "string" ? data.error : `${response.status} ${response.statusText}`;
    throw new Error(message);
  }
  return data;
}
