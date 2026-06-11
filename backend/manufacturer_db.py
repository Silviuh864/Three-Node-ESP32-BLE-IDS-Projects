
import yaml
import os

_db = {}      # { "0x004C": "Apple, Inc." }
_loaded = False

YAML_PATH = os.path.join(os.path.dirname(__file__), "company_identifiers.yaml.txt")


def _normalizeaza_id(raw) -> str:
    """
    Acceptă int (ex: 0x004C din YAML) sau str (ex: '0x004c', '0x4C')
    și returnează forma canonică '0xXXXX' uppercase.
    """
    try:
        if isinstance(raw, int):
            return f"0x{raw:04X}"
        return f"0x{int(str(raw), 16):04X}"
    except (ValueError, TypeError):
        return str(raw).upper()


def incarca_yaml(path: str = None) -> bool:
    """
    Încarcă baza de date din fișierul YAML oficial BT SIG.
    Returnează True dacă s-a încărcat cu succes.
    """
    global _db, _loaded
    target = path or YAML_PATH

    if not os.path.exists(target):
        print(f"[MFR_DB] AVERTISMENT: Fișierul '{target}' nu a fost găsit.")
        _loaded = False
        return False

    try:
        with open(target, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        entries = data.get("company_identifiers", [])
        _db = {}
        for entry in entries:
            if "value" in entry and "name" in entry:
                key = _normalizeaza_id(entry["value"])
                _db[key] = entry["name"]

        _loaded = True
        print(f"[MFR_DB] Încărcat: {len(_db)} producători din '{os.path.basename(target)}'")
        return True

    except Exception as e:
        print(f"[MFR_DB] EROARE la încărcarea YAML: {e}")
        _loaded = False
        return False


def resolve_manufacturer(hex_id: str) -> str:
    """
    Primește un manufacturer ID (ex: '0x004C', '0xffff', '0x4c')
    și returnează numele companiei pentru afișare în tabel.

    Exemple:
      '0x004C' -> 'Apple, Inc.'
      '0xFFFF' -> '0xFFFF — nealocat'
      '0xABCD' -> '0xABCD — necunoscut'
    """
    if not _loaded:
        return hex_id

    normalized = _normalizeaza_id(hex_id)

    if normalized == "0xFFFF":
        return f"{normalized} — nealocat"
    if normalized == "0x0000":
        return f"{normalized} — rezervat"

    name = _db.get(normalized)
    if name:
        return name

    return f"{normalized} — necunoscut"


def resolve_manufacturer_full(hex_id: str) -> dict:
    """Returnează dict cu id și name — util pentru extinderi viitoare."""
    normalized = _normalizeaza_id(hex_id)
    name = _db.get(normalized, "Necunoscut") if _loaded else "YAML neîncărcat"
    return {"id": normalized, "name": name}


# --- Inițializare automată la import ---
incarca_yaml()
