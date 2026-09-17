/** Coerce API list-or-string fields without parsing DB JSON in the browser. */
export function asStringList(value) {
  if (value == null) return []
  if (Array.isArray(value)) return value.map((v) => String(v).trim()).filter(Boolean)
  if (typeof value === 'string' && value.trim()) return [value.trim()]
  return []
}
