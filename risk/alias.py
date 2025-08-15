\
def load_alias_map(path: str) -> dict:
    """Load alias mappings from alias.txt where each line is 'alias=ISO2'.
    Keys are case-insensitive (lowercased), values are UPPER ISO2.
    Lines starting with # are comments.
    """
    mapping = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                mapping[k.strip().lower()] = v.strip().upper()
    except FileNotFoundError:
        pass
    return mapping
