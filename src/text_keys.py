"""Clave de formato, escritura final por tipo de columna, firma de números y similitud (spec 002)."""
import math
import re
import unicodedata

import pandas as pd
from rapidfuzz import fuzz

COLUMN_TYPES = {
    "TIPO DE EXPEDIENTE": "fixed_list",
    "DELEGADA": "fixed_list",
    "SALA": "short_code",
    "SOLICITUD": "category",
    "DECISIÓN": "category",
    "PERTENECE": "category",
    "NOMBRES_APELLIDOS": "proper_name",
    "MAGISTRADO": "proper_name",
    "FUNCIONARIO A CARGO": "proper_name",
    "IDENTIFICACIÓN": "identification",
}

# En estas dos columnas un salto de línea separa personas: no es formato.
LINE_SEPARATED_COLUMNS = {"NOMBRES_APELLIDOS", "IDENTIFICACIÓN"}

# Definición "Partículas" de la spec 002 (cambio 2: EL, AL y A).
PARTICLES = {"DE", "DEL", "LA", "LAS", "LOS", "EL", "AL", "A", "Y"}

_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿"))
# Acento agudo y grave. La virgulilla de la Ñ (U+0303) y la diéresis de la Ü
# (U+0308) no se quitan: son letras distintas, no tildes.
_VOWEL_ACCENTS = {"́", "̀"}
_PUNCTUATION = re.compile(r"[^\w\s]|_")
_DIGITS = re.compile(r"\d+")


def to_text(value) -> str:
    """
    Texto de un valor tal como llega de Excel: vacío si es nulo, y sin ".0"
    cuando Excel guarda como número decimal algo que es entero (una cédula
    12345678 llega como 12345678.0) — RF-35.
    """
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ""
    if isinstance(value, float) and not math.isinf(value) and value.is_integer():
        return str(int(value))
    return str(value)


def strip_vowel_accents(text: str) -> str:
    """Quita tildes de las vocales; conserva Ñ y Ü."""
    decomposed = unicodedata.normalize("NFD", text)
    return unicodedata.normalize("NFC", "".join(c for c in decomposed if c not in _VOWEL_ACCENTS))


def has_vowel_accent(value) -> bool:
    """Si el texto tiene alguna vocal con tilde (la Ñ y la Ü no cuentan)."""
    return any(c in _VOWEL_ACCENTS for c in unicodedata.normalize("NFD", to_text(value)))


def _normalize_spacing(text: str, keep_line_breaks: bool) -> str:
    """
    Un solo espacio entre palabras y nada al inicio ni al final. Los espacios
    invisibles (nbsp y similares) cuentan como espacio porque str.split() los
    reconoce. Si keep_line_breaks, cada línea se normaliza por separado y se
    descartan las líneas vacías.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not keep_line_breaks:
        return " ".join(text.split())
    lines = (" ".join(line.split()) for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def format_key(value, column=None) -> str:
    """
    Clave para comparar valores sin sus diferencias de formato (definición de
    la spec 002): mayúsculas, sin tildes en las vocales (conserva Ñ y Ü),
    signos de puntuación como espacio y un solo espacio entre palabras. Los
    saltos de línea son espacio salvo en NOMBRES_APELLIDOS e IDENTIFICACIÓN.
    """
    text = to_text(value).translate(_ZERO_WIDTH)
    text = strip_vowel_accents(text.upper())
    text = _PUNCTUATION.sub(" ", text)
    return _normalize_spacing(text, column in LINE_SEPARATED_COLUMNS)


def render(value, column) -> str:
    """
    Escritura final de un valor en su columna: mayúsculas y espaciado limpio
    en todas (RF-7); en los nombres propios, además, sin tildes en las
    vocales pero con Ñ y Ü (RF-8). Los signos de puntuación se conservan.
    """
    text = to_text(value).translate(_ZERO_WIDTH).upper()
    if COLUMN_TYPES.get(column) == "proper_name":
        text = strip_vowel_accents(text)
    return _normalize_spacing(text, column in LINE_SEPARATED_COLUMNS)


def number_signature(text) -> tuple[int, ...]:
    """Números que contiene un valor, por su valor ("003" y "3" son iguales) — RF-17."""
    return tuple(int(n) for n in _DIGITS.findall(to_text(text)))


def has_negation(key: str) -> bool:
    """Si una clave de formato tiene la palabra NO suelta (RF-82, Decisión #14)."""
    return "NO" in key.split()


def content_word_count(key: str) -> int:
    """Palabras de una clave de formato sin contar partículas (RF-83)."""
    return sum(1 for word in key.split() if word not in PARTICLES)


def similarity(key_a: str, key_b: str) -> float:
    """
    Similitud de 0 a 100 entre dos claves de formato: fuzz.ratio de
    rapidfuzz (Indel normalizado), Decisión #2 del plan.
    """
    return fuzz.ratio(key_a, key_b)


# Cambio 5: prefijos que vuelven una palabra su contraria (RF-86).
NEGATING_PREFIXES = ("IN", "IM", "DES", "DIS")


def _content_words(key: str) -> list[str]:
    return [word for word in key.split() if word not in PARTICLES]


def negates(key_a: str, key_b: str) -> bool:
    """
    RF-86: una palabra de una clave es la de la otra con un prefijo que la
    niega ("CUMPLIMIENTO" / "INCUMPLIMIENTO", "ARCHIVAR" / "DESARCHIVAR").
    La palabra base tiene 5 letras o más, para no confundir palabras cortas.
    """
    a, b = set(_content_words(key_a)), set(_content_words(key_b))
    for word in a ^ b:
        for base in (a | b) - {word}:
            if (len(base) >= 5 and (word in a) != (base in a)
                    and any(word == prefix + base for prefix in NEGATING_PREFIXES)):
                return True
    return False


def is_slight_typo(word_a: str, word_b: str) -> bool:
    """
    Error de tipeo leve entre dos palabras: de 5 letras o más, similitud de
    90 o más, y sin que una sea la otra con letras de más al comienzo
    ("CONOCIMEINTO" / "CONOCIMIENTO" sí; "CUMPLIMIENTO" / "INCUMPLIMIENTO" no).
    """
    if word_a == word_b or word_a.endswith(word_b) or word_b.endswith(word_a):
        return False
    return min(len(word_a), len(word_b)) >= 5 and fuzz.ratio(word_a, word_b) >= 90


def _word_change(word_a: str, word_b: str) -> str | None:
    if word_a == word_b:
        return ""
    if word_a + "S" == word_b or word_b + "S" == word_a or word_a + "ES" == word_b or word_b + "ES" == word_a:
        return "singular/plural"
    if is_slight_typo(word_a, word_b):
        return "error de tipeo leve"
    return None


def obvious_difference(key_a: str, key_b: str) -> str | None:
    """
    Definición "diferencia muy obvia" (cambio 5, RF-85): las mismas palabras,
    una por una y en orden, sin contar partículas, salvo singular/plural o un
    tipeo leve; con los mismos números, el mismo NO y sin prefijos que niegan.
    Devuelve qué cambia ("" si solo cambian partículas o signos), o None.
    """
    if (has_negation(key_a) != has_negation(key_b)
            or number_signature(key_a) != number_signature(key_b)
            or negates(key_a, key_b)):
        return None
    a, b = _content_words(key_a), _content_words(key_b)
    if not a or len(a) != len(b):
        return None
    changes = [_word_change(x, y) for x, y in zip(a, b)]
    if None in changes:
        return None
    return " + ".join(sorted({change for change in changes if change}))
