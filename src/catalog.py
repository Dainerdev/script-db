"""Grupos de variantes y valor del catálogo de cada grupo (spec 002)."""
from collections import Counter, defaultdict

from rapidfuzz import fuzz, process

from src.text_keys import (
    COLUMN_TYPES,
    content_word_count,
    format_key,
    has_negation,
    has_vowel_accent,
    negates,
    number_signature,
    render,
    strip_vowel_accents,
    to_text,
)

GROUP_THRESHOLD = 80

# SALA (RF-15) e IDENTIFICACIÓN no se agrupan por parecido: "SR" y "SRV" son
# salas distintas, y dos cédulas parecidas son dos personas.
_UNGROUPED_TYPES = {"short_code", "identification"}


def _rows_by_key(value_counts, column) -> Counter:
    """Filas por clave de formato: suma las variantes que solo difieren en formato."""
    rows = Counter()
    for value, count in value_counts.items():
        key = format_key(value, column)
        if key:
            rows[key] += count
    return rows


def signature(key: str, column_type) -> tuple:
    """
    Lo que dos claves tienen que compartir para poder ser del mismo grupo:
    los mismos números (RF-17), las dos con NO o las dos sin NO (RF-82) y,
    en las categorías, la misma cantidad de palabras sin partículas (RF-83).
    """
    words = content_word_count(key) if column_type == "category" else None
    return number_signature(key), has_negation(key), words


def group(value_counts, column) -> dict[str, str]:
    """
    Grupos de variantes de una columna (definición de la spec 002, RF-2,
    RF-14, RF-15, RF-17). Recibe cada valor crudo con su cantidad de filas y
    devuelve, para cada clave de formato, la clave que abrió su grupo. Los
    vacíos no forman grupo.

    Se recorren las claves de más a menos filas (empate: orden alfabético,
    para que el resultado no dependa del orden de entrada). Una clave se une
    al grupo de la apertura más parecida con similitud de 80 o más y la
    misma firma (signature); si no hay ninguna, abre su propio grupo. Se compara
    contra TODAS las aperturas, sin bloques por prefijo, para ver también
    los typos en las primeras letras (Decisión #3 del plan). Ante un empate
    de similitud gana el grupo con más filas.
    """
    rows = _rows_by_key(value_counts, column)
    column_type = COLUMN_TYPES.get(column)
    if column_type in _UNGROUPED_TYPES:
        return {key: key for key in rows}

    openers: list[str] = []
    opener_signature: dict[str, tuple] = {}
    group_rows: dict[str, int] = {}
    members: dict[str, list[str]] = {}
    assignment: dict[str, str] = {}

    for key in sorted(rows, key=lambda k: (-rows[k], k)):
        key_signature = signature(key, column_type)
        matches = [
            (opener, score, index)
            for opener, score, index in process.extract(
                key, openers, scorer=fuzz.ratio, score_cutoff=GROUP_THRESHOLD, limit=None
            )
            # RF-86: ni la apertura ni nadie del grupo puede ser su contrario.
            if opener_signature[opener] == key_signature
            and not any(negates(key, member) for member in members[opener])
        ]
        if matches:
            opener = max(matches, key=lambda m: (m[1], group_rows[m[0]], -m[2]))[0]
        else:
            opener = key
            openers.append(key)
            opener_signature[key] = key_signature
            group_rows[key] = 0
            members[key] = []
        assignment[key] = opener
        members[opener].append(key)
        group_rows[opener] += rows[key]

    return assignment


def _most_rows(rows_by_item) -> str:
    """El de más filas; empate: orden alfabético (mismo criterio que group)."""
    return min(rows_by_item, key=lambda item: (-rows_by_item[item], item))


def _repeats_another(word: str, words: set[str]) -> bool:
    """Si la palabra es otra del mismo valor repetida con un error (similitud de 80 o más)."""
    return len(word) >= 5 and any(
        len(other) >= 5 and fuzz.ratio(word, other) >= GROUP_THRESHOLD for other in words - {word}
    )


def _contains_all_words(bigger: str, smaller: str) -> bool:
    """
    Todas las palabras de smaller y alguna distinta más (RF-62). Repetir una
    no cuenta, y tampoco una que es otra del mismo valor repetida con un
    error (cambio 5: "BENITEZ BENITJEZ" y "BENITES BENITEZ" no son más
    completas que "BENITEZ BENITEZ"; BENITES / BENITEZ se parecen 85,7).
    """
    big, small = set(bigger.split()), set(smaller.split())
    if not big > small:
        return False
    return any(not _repeats_another(extra, big) for extra in big - small)


def _differs_only_in_enie(a: str, b: str) -> bool:
    return a != b and a.replace("Ñ", "N") == b.replace("Ñ", "N")


def _borrow_accents(text: str, rendered_variants: Counter) -> str:
    """
    RF-7: una palabra sin tilde toma la escritura con tilde que traiga alguna
    variante del grupo ("ACCION DE TUTELA" + "ACCIÓN DE TUTELAR" → "ACCIÓN DE
    TUTELA"). Si hay varias escrituras con tilde, la de más filas.
    """
    accented = defaultdict(Counter)
    for variant, rows in rendered_variants.items():
        for word in variant.split():
            if has_vowel_accent(word):
                accented[strip_vowel_accents(word)][word] += rows
    return " ".join(
        _most_rows(accented[word]) if word in accented else word
        for word in text.split()
    )


def representative(variant_counts, column) -> str:
    """
    Valor del catálogo de un grupo (RF-5 a RF-8, RF-62 a RF-64). Recibe los
    valores crudos de UN grupo con su cantidad de filas y devuelve el valor
    ya escrito con la ortografía de su columna; texto vacío si el grupo no
    tiene valores.

    1. Entre las claves del grupo, la de más filas (RF-6); si otra contiene
       todas sus palabras y alguna más, la más completa — entre varias, la de
       más filas (RF-62). En nombres propios, si otra difiere solo en tener Ñ
       donde esta tiene N, la de Ñ (RF-64).
    2. Entre las escrituras de esa clave (que difieren solo en formato), en
       columnas que no son de nombre, la con tildes de más filas; si ninguna
       tiene tildes, la de más filas (RF-5).
    3. Se escribe con la ortografía de la columna (RF-7, RF-8, RF-63) y, fuera
       de los nombres, cada palabra sin tilde toma la que traiga otra variante
       del grupo (RF-7).
    """
    raw_by_key: dict[str, Counter] = defaultdict(Counter)
    for value, count in variant_counts.items():
        key = format_key(value, column)
        if key:
            raw_by_key[key][to_text(value)] += count
    if not raw_by_key:
        return ""

    rows = {key: raws.total() for key, raws in raw_by_key.items()}
    is_name = COLUMN_TYPES.get(column) == "proper_name"

    chosen = _most_rows(rows)
    more_complete = {key: n for key, n in rows.items() if _contains_all_words(key, chosen)}
    if more_complete:
        chosen = _most_rows(more_complete)
    if is_name:
        with_enie = {
            key: n for key, n in rows.items()
            if _differs_only_in_enie(chosen, key) and key.count("Ñ") > chosen.count("Ñ")
        }
        if with_enie:
            chosen = _most_rows(with_enie)

    raws = raw_by_key[chosen]
    if not is_name:
        raws = Counter({raw: n for raw, n in raws.items() if has_vowel_accent(raw)}) or raws
    text = render(_most_rows(raws), column)
    if is_name:
        return text

    rendered = Counter()
    for raws_of_key in raw_by_key.values():
        for raw, n in raws_of_key.items():
            rendered[render(raw, column)] += n
    return _borrow_accents(text, rendered)
