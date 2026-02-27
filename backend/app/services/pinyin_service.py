from pypinyin import pinyin, Style, lazy_pinyin


def get_pinyin_full(name: str) -> str:
    """Get full pinyin of a Chinese name. e.g., '张三' -> 'zhangsan'"""
    return "".join(lazy_pinyin(name)).lower()


def get_pinyin_initials(name: str) -> str:
    """Get pinyin initials. e.g., '张三' -> 'zs'"""
    result = pinyin(name, style=Style.FIRST_LETTER)
    return "".join(item[0] for item in result).lower()


def get_pinyin_data(name: str) -> tuple[str, str]:
    """Returns (full_pinyin, initials) for a given name."""
    return get_pinyin_full(name), get_pinyin_initials(name)


def match_pinyin(query: str, name: str, name_pinyin: str, name_initials: str) -> bool:
    """Check if a query matches a name via pinyin fuzzy matching.

    Matches against:
    - Original name (case-insensitive)
    - Full pinyin
    - Pinyin initials
    """
    q = query.lower().strip()
    if not q:
        return True

    # Direct name match
    if q in name.lower():
        return True

    # Full pinyin match
    if q in name_pinyin.lower():
        return True

    # Initials match
    if q in name_initials.lower():
        return True

    return False
