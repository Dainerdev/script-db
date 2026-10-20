"""Separación de comparecientes y de las líneas que no son personas (spec 002)."""
import re
from collections import Counter
from dataclasses import dataclass, field
from functools import cache

import numpy as np
import pandas as pd

from src.parameters import DECISION_ACCEPT, DECISION_KEEP, MARK_NOT_A_PERSON, MARK_PENDING, is_case_reference
from src.text_keys import PARTICLES, format_key, to_text

NAMES = "NOMBRES_APELLIDOS"
IDENTIFICATION = "IDENTIFICACIÓN"

# Palabras de asunto (definición "Asunto", Decisión #6): la lista inicial es
# la del informe de hallazgos del 2026-09-25; el equipo la amplía acá. Se
# comparan contra la clave de formato (mayúsculas, sin tildes) y aceptan el
# plural ("INFORMES", "INVITACIONES").
SUBJECT_WORDS = frozenset({
    "SOLICITUD", "INVITACION", "REQUERIMIENTO", "TRASLADO", "RESPUESTA", "INFORME", "SITUACION",
    "COMUNICACION", "AUTO", "CORRECCION", "EMPLAZAMIENTO", "NOTIFICACION", "PRIORIZA", "ACOPIO",
    "ENTREGA", "LLAMAMIENTO", "RECLUTAMIENTO", "BIENES", "MUERTES", "CONVOCATORIA", "OFICIO",
    "REMISION", "SEGUIMIENTO", "AUDIENCIA", "MESA", "PETICION", "DERECHO",
    # Cambio 11 (plan, decisión 6): asuntos que el corte real traía en esta
    # columna. Medidas cautelares y macrocasos (palabras de 40 líneas o más
    # que casi nunca son nombre ni apellido en el diccionario del archivo):
    "MEDIDA", "CAUTELAR", "CEMENTERIO", "SUBCASO", "CRIMEN", "CONFLICTO", "COMETIDO", "COMETIDA",
    "VIOLENCIA", "SEXUAL", "PREJUICIO", "REPRODUCTIVA", "ORIENTACION", "IDENTIDAD", "DISCRIMINACION",
    "CUADERNO", "MUNICIPIO", "MUNICIPAL", "CONTRAINTELIGENCIA", "LOGISTICA", "ASESINATO", "DESAPARICION",
    "FORZADA", "FORZADO", "ETNICO", "RESGUARDO", "TERRITORIO", "COMBATE", "COMBATIENTE", "AMNISTIABLE",
    "VEREDA", "UTILIZACION", "PARAMILITAR", "ACREDITACION", "RESTAURACION", "ECOSISTEMA", "BRIGADA",
    "INTELIGENCIA", "MAGNICIDIO", "INVESTIGACION", "DESPLAZAMIENTO", "MOVILIZACION", "ORGANIZACION",
    "ARTILLERIA", "INHUMACION", "VICTIMIZACION", "REHEN", "PRIVACION", "RETENCION", "ILEGAL", "ESCOMBRERA",
    "MOVICE",
    # entidades:
    "FISCALIA", "DEFENSORIA", "PROCURADURIA", "MINISTERIO", "JUZGADO", "TRIBUNAL", "COMISION", "CONSEJO",
    "CORPORACION", "FUNDACION", "ASOCIACION", "COLECTIVO", "MOVIMIENTO", "COMPARECIENTE", "ALCALDIA",
    "GOBERNACION", "PERSONERIA", "EJERCITO", "POLICIA", "UNIDAD",
    # roles (el abogado o apoderado no es compareciente):
    "ABOGADO", "ABOGADA", "APODERADO", "APODERADA", "DEFENSOR", "DEFENSORA", "DR", "DRA", "DOCTOR", "DOCTORA",
    # Fuera a propósito: VICTIMA (va pegada a nombres reales), PERSONA y las
    # que también son nombres o apellidos (SALA, CORTE, MAGDALENA, NIÑO…).
})
# Palabras de asunto que también son apellidos: cuentan solo como primera
# palabra de la línea (cambio 7: MESA era apellido en 436 de 537 líneas).
# Cambio 11: los roles también ("(Abogado)", "Dr. …"); en otro lugar de la
# línea pueden ser un apellido ("Juan Carlos Defensor") o acompañar el
# nombre de la persona, que no se debe perder.
SUBJECT_FIRST_WORD_ONLY = frozenset({
    "MESA", "ABOGADO", "ABOGADA", "APODERADO", "APODERADA", "DEFENSOR", "DEFENSORA", "DR", "DRA", "DOCTOR",
    "DOCTORA",
})

# Clases de línea de NOMBRES_APELLIDOS.
PERSON, SUBJECT, CASE_REFERENCE, EMPTY = "persona", "asunto", "referencia de caso", "vacía"
OTHER_CATEGORY = "otra categoría"     # dígitos y menos de dos palabras con letras (cambio 7)
# Valores de la columna "SEPARACIÓN" (RF-22, RF-25).
SEPARATED, UNCONFIRMED, NOT_SEPARATED = "SEPARADA", "SEPARADA SIN CONFIRMAR", "SIN SEPARAR"
# Marcas de fila para "Observación estandarización" (RF-78).
NOT_A_PERSON = MARK_NOT_A_PERSON
MORE_UNNAMED = "hay más comparecientes sin nombrar"
PENDING = MARK_PENDING
LINES_REMOVED = "se quitaron líneas que no son de persona"     # RF-68 (cambio 11)

MAX_CONTENT_WORDS = 5          # definición "Celda con varios nombres"
MIN_DICTIONARY_COUNT = 3       # Decisión #16
_SEPARATORS = re.compile(r"\s+Y\s+|[,;]", re.IGNORECASE)
# RF-100: solo " Y " y ";" vuelven la línea "celda con varios nombres"; la
# coma no, porque separa apellidos de nombres ("GÓMEZ RUIZ, JUAN CARLOS").
_STRONG_SEPARATORS = re.compile(r"\s+Y\s+|;", re.IGNORECASE)
# Definición "Anotación" (cambio 11): empieza con "(", aunque antes haya comillas.
_ANNOTATION = re.compile(r"""^["“”'«»\s]*\(""")
# Definición "Referencia de caso" (cambio 11): la línea empieza con un caso,
# con o sin "No." antes del número, y puede seguir texto.
_CASE_START = re.compile(r"([A-Z]+)\s?(?:NO?\s)?([0-9O]*\d[0-9O]*)(?=\s|$)")

_MORE = re.compile(r"\s*\bY\s+(?:OTROS|\d+\s+PERSONAS?\s+M[AÁ]S)\b\s*(?:\(\s*\d+\s*\))?\s*$", re.IGNORECASE)
_THOUSANDS_DOT = re.compile(r"(?<=\d)\.(?=\d{3}(?!\d))")
_CEDULA_NUMBER = re.compile(r"(?<!\d)\d{5,15}(?!\d)")


@dataclass(frozen=True)
class Trace:
    """Entrada del rastro de una celda de nombres que cambió (RF-29, RF-68, RF-75)."""
    row_id: int
    original: str
    final: str          # las personas que quedaron, separadas por " | "
    motive: str


@dataclass
class SeparationResult:
    """
    DataFrame con una fila por persona, marcas por (_row_id, _person), rastro
    y celdas pendientes: {_row_id: sugerencia con las partes separadas por
    " | ", o "" si no hay} (RF-25, RF-69).
    """
    df: pd.DataFrame
    marks: dict = field(default_factory=dict)
    traces: list = field(default_factory=list)
    pending: dict = field(default_factory=dict)
    applied_decisions: set = field(default_factory=set)   # celdas que separó o mantuvo una decisión (T12)


def _fold(key: str) -> str:
    """Para buscar nombres, la Ñ cuenta como N (PEÑALOZA y PENALOZA son la misma persona)."""
    return key.replace("Ñ", "N")


def _content(words) -> list[str]:
    return [word for word in words if word not in PARTICLES]


def _is_name_shape(words) -> bool:
    """Forma de un nombre completo: de 2 a 5 palabras sin partículas (cambio 8, RF-24, RF-69)."""
    return 2 <= len(_content(words)) <= MAX_CONTENT_WORDS


@dataclass
class NameDictionary:
    """
    Diccionario de nombres del archivo (Decisión #16): sale de las filas con
    una sola línea de persona y una sola cédula. La primera palabra (sin
    partículas) cuenta como nombre de pila y las dos últimas como apellidos;
    una palabra vale con 3 apariciones o más, y solo en el papel en que es
    más común.
    """
    first: Counter = field(default_factory=Counter)
    last: Counter = field(default_factory=Counter)

    @classmethod
    def build(cls, names) -> "NameDictionary":
        dictionary = cls()
        for name in names:
            words = [w for w in _content(_fold(format_key(name, NAMES)).split()) if not w.isdigit()]
            if len(words) < 2:
                continue
            dictionary.first[words[0]] += 1
            for word in (words[-2:] if len(words) >= 3 else words[-1:]):
                dictionary.last[word] += 1
        return dictionary

    def is_first(self, word: str) -> bool:
        return self.first[word] >= MIN_DICTIONARY_COUNT and self.first[word] > self.last[word]

    def is_last(self, word: str) -> bool:
        return self.last[word] >= MIN_DICTIONARY_COUNT and self.last[word] > self.first[word]

    def division(self, words: list[str]) -> tuple[tuple[int, int], ...] | None:
        """Cortes donde un nombre de pila sigue justo a un apellido; cada parte con forma de nombre."""
        folded = [_fold(word) for word in words]
        cuts = [i for i in range(1, len(words)) if self.is_first(folded[i]) and self.is_last(folded[i - 1])]
        if not cuts:
            return None
        bounds = [0, *cuts, len(words)]
        spans = tuple(zip(bounds, bounds[1:]))
        if all(_is_name_shape(words[a:b]) for a, b in spans):
            return spans
        return None


def count_cedulas(value) -> int:
    """
    Definición "Cantidad de cédulas" (cambio 6): cuántos números de 5 a 15
    dígitos hay después de quitar los puntos de miles ("12.345.678" es uno;
    "123456 y 654321", dos). Un punto seguido de más de tres dígitos no es
    de miles: "12345678.87654321" son dos cédulas.
    """
    return len(_CEDULA_NUMBER.findall(_THOUSANDS_DOT.sub("", to_text(value))))


def _subject_base(word: str) -> str | None:
    """La palabra de asunto que es `word`, en singular o plural (S, ES), o None."""
    for base in (word, word[:-1] if word.endswith("S") else None, word[:-2] if word.endswith("ES") else None):
        if base in SUBJECT_WORDS:
            return base
    return None


def _is_subject_word(word: str, first: bool = False) -> bool:
    base = _subject_base(word)
    return base is not None and (first or base not in SUBJECT_FIRST_WORD_ONLY)


def _starts_with_case(key: str) -> bool:
    """
    La clave empieza con "CASO" y un número, aunque siga texto ("CASO 004
    SUBCASO URABA", cambio 11). Sin la tolerancia de una letra de
    `is_case_reference`: con texto detrás, CARO o CASA serían un apellido.
    """
    start = _CASE_START.match(key)
    return bool(start) and start[1] == "CASO"


def classify_line(line) -> str:
    """
    Clase de una línea de NOMBRES_APELLIDOS (definiciones "Asunto" y "Línea
    de persona", cambio 7): vacía, referencia de caso, asunto, otra categoría
    (dígitos y menos de dos palabras con letras, como "12345678" o "No. 45")
    o persona.
    """
    key = format_key(line, NAMES)
    if not key:
        return EMPTY
    if is_case_reference(line) or _starts_with_case(key):
        return CASE_REFERENCE
    words = key.split()
    if any(_is_subject_word(word, first=(i == 0)) for i, word in enumerate(words)):
        return SUBJECT
    if any(ch.isdigit() for ch in key) and sum(1 for word in words if not word.isdigit()) < 2:
        return OTHER_CATEGORY
    return PERSON


def _known_partitions(words: list[str], known: set[str], limit: int = 20) -> list[tuple[tuple[int, int], ...]]:
    """
    Formas de cortar la línea en dos o más tramos seguidos, cada uno un
    nombre conocido (que ya tiene forma de nombre, cambio 8) (RF-24, RF-69),
    por programación dinámica. `limit` evita una explosión de combinaciones
    en textos largos.
    """
    folded = [_fold(word) for word in words]

    @cache
    def from_word(start: int) -> tuple:
        if start == len(folded):
            return ((),)
        found = []
        for end in range(start + 2, len(folded) + 1):
            if " ".join(folded[start:end]) in known:
                for rest in from_word(end):
                    found.append(((start, end), *rest))
                    if len(found) >= limit:
                        return tuple(found)
        return tuple(found)

    return [partition for partition in from_word(0) if len(partition) >= 2]


def _separator_division(line: str, separators=_SEPARATORS) -> tuple[str, ...] | None:
    """
    Partes separadas por " Y ", coma o punto y coma, si cada una es una línea
    de persona con forma de nombre (RF-69, cambio 8). Con
    `_STRONG_SEPARATORS`, sin la coma (RF-100).
    """
    parts = [part.strip() for part in separators.split(line)]
    keys = tuple(format_key(part, NAMES) for part in parts)
    if (len(parts) >= 2 and all(classify_line(part) == PERSON for part in parts)
            and all(_is_name_shape(key.split()) for key in keys)):
        return keys
    return None


def _choose(divisions: list[tuple[str, ...]], cedulas: int) -> tuple[str, ...] | None:
    """
    Regla de desempate de RF-69: con cédulas, la única división que tiene
    tantas partes como cédulas; sin cédulas, o si ninguna coincide, solo si
    todas las divisiones posibles son la misma.
    """
    distinct = list(dict.fromkeys(divisions))
    if cedulas:
        matching = [division for division in distinct if len(division) == cedulas]
        if matching:
            return matching[0] if len(matching) == 1 else None
    return distinct[0] if len(distinct) == 1 else None


def _original_tokens(line: str, words: list[str]) -> list[str]:
    """Las palabras del texto original si calzan una a una con las de la clave; si no, las de la clave."""
    tokens = line.split()
    if len(tokens) == len(words) and all(format_key(token, NAMES) == word for token, word in zip(tokens, words)):
        return tokens
    return words


def _strip_more(line: str) -> tuple[str, bool]:
    """Quita "Y OTROS" / "Y N PERSONAS MÁS" del final de la línea (RF-29)."""
    match = _MORE.search(line)
    if match:
        return line[:match.start()].strip(), True
    return line, False


def _split_cell(value, cedulas: int = 0) -> tuple[list[str] | None, bool, bool, bool]:
    """
    Personas de una celda de nombres: (personas o None si la celda no tiene
    texto, si traía "Y OTROS", si se quitaron líneas que no son de persona,
    si todas sus líneas son asuntos o referencias de caso). Las anotaciones
    entre paréntesis se quitan como las demás líneas que no son de persona,
    salvo que las `cedulas` de la celda alcancen para contarlas (cambio 11).
    """
    text = to_text(value).replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return None, False, False, False
    candidates, kinds, more = [], [], False
    for line in lines:
        base, had_more = _strip_more(line)
        more = more or had_more
        kind = classify_line(base)
        kinds.append(kind)
        if kind == PERSON:
            candidates.append((base, bool(_ANNOTATION.match(base))))
    plain = [base for base, annotation in candidates if not annotation]
    annotations_out = bool(plain) and len(plain) < len(candidates) and cedulas < len(candidates)
    persons = plain if annotations_out else [base for base, _ in candidates]
    not_person = [kind for kind in kinds if kind in (SUBJECT, CASE_REFERENCE, OTHER_CATEGORY)]
    removed = bool(persons) and (bool(not_person) or annotations_out)              # RF-68
    only_subjects = not persons and bool(not_person) and all(
        kind in (SUBJECT, CASE_REFERENCE) for kind in not_person)                  # RF-28
    return persons, more, removed, only_subjects


def _single_word(line: str) -> bool:
    """Una línea de una sola palabra sin contar partículas (RF-99)."""
    return len(_content(format_key(line, NAMES).split())) <= 1


def _joined_suggestion(persons: list[str]) -> str:
    """
    RF-99: cada línea de una palabra se une a la línea de persona anterior (a
    la siguiente, si es la primera); las partes, con " | ".
    """
    parts, carry = [], ""
    for line in persons:
        key = format_key(line, NAMES)
        if _single_word(line) and parts:
            parts[-1] = f"{parts[-1]} {key}"
        elif _single_word(line):
            carry = f"{carry} {key}".strip()
        else:
            parts.append(f"{carry} {key}".strip())
            carry = ""
    if carry:
        parts.append(carry)
    return " | ".join(parts)


def _separation_decisions(decisions, name_col) -> dict:
    """
    Decisiones de la tabla que separan o mantienen una celda de nombres
    (RF-39): partes con " | ", o ACEPTAR/MANTENER. Un par con dos decisiones
    distintas no se usa (RF-48; lo lista `standardize_parameters`).
    """
    if decisions is None:
        return {}
    texts = {}
    for column, value, text in decisions.table:
        text = to_text(text).strip()
        if to_text(column).strip() == name_col and ("|" in text or text.upper() in (DECISION_ACCEPT, DECISION_KEEP)):
            texts.setdefault(to_text(value).strip(), set()).add(text if "|" in text else text.upper())
    return {key: next(iter(found)) for key, found in texts.items() if len(found) == 1}


def separate(df: pd.DataFrame, name_col: str = NAMES, id_col: str = IDENTIFICATION,
             decisions=None) -> SeparationResult:
    """
    Una fila por compareciente (RF-22 a RF-29, RF-67, RF-68, RF-70; cambio 6).
    Cada línea de persona de NOMBRES_APELLIDOS pasa a su propia fila, con la
    IDENTIFICACIÓN completa (sin repartir cédulas), "No", RADICADO IUS y los
    demás valores repetidos. "SEPARACIÓN" dice SEPARADA si la cantidad de
    cédulas es igual a la de personas y SEPARADA SIN CONFIRMAR si no (también
    sin la columna IDENTIFICACIÓN, RF-70). Las líneas que no son de persona
    no crean filas (RF-68); una celda de solo asuntos o referencias de caso
    queda entera y marcada "no es una persona" (RF-28); "Y OTROS" se quita y
    marca la fila (RF-29). Cada fila hereda `_row_id` (si falta, la posición
    de la fila) y suma `_person`, "ID REGISTRO" (`_row_id` + 1, Decisión
    #15), "PERSONA N.º" y "PERSONAS EN EL REGISTRO" (RF-27).
    Una celda de una sola línea con varios nombres (más de 5 palabras sin
    partículas, o 2 cédulas o más) se separa si su texto se divide de una
    sola manera en tantos nombres conocidos como cédulas (RF-24); si no,
    queda en una fila, SIN SEPARAR y pendiente, con la sugerencia de RF-69
    (RF-25, RF-26). Los nombres conocidos y el diccionario salen del mismo
    archivo, por eso hay dos pasadas. `decisions` (T12): una decisión con
    partes separadas por " | " separa la celda así (SEPARADA si hay tantas
    cédulas como partes, si no SEPARADA SIN CONFIRMAR, RF-48); ACEPTAR usa
    la sugerencia de una celda pendiente; MANTENER la deja en una fila, sin
    pendiente. Cambio 11: las anotaciones entre paréntesis no crean filas
    (salvo que las cédulas alcancen), una celda de varias líneas con alguna
    de una sola palabra queda SIN SEPARAR con la sugerencia de unirla
    (RF-99), y las filas de una celda a la que se le quitaron líneas llevan
    la marca LINES_REMOVED (RF-68).
    """
    df = df.reset_index(drop=True)
    if "_row_id" not in df.columns:
        df["_row_id"] = range(len(df))
    has_names, has_ids = name_col in df.columns, id_col in df.columns
    empty_cell = (None, False, False, False)
    cedulas = [count_cedulas(value) for value in df[id_col]] if has_ids else [0] * len(df)
    cells = ([_split_cell(value, count) for value, count in zip(df[name_col], cedulas)] if has_names
             else [empty_cell] * len(df))

    singles = [(cell[0][0], count) for cell, count in zip(cells, cedulas) if cell[0] and len(cell[0]) == 1]
    known = {_fold(key) for key in (format_key(name, NAMES) for name, _ in singles) if _is_name_shape(key.split())}
    dictionary = NameDictionary.build(name for name, count in singles if count == 1)

    by_cell = _separation_decisions(decisions, name_col) if has_names else {}
    names, statuses, counts = [], [], []
    marks, traces, pending, applied = {}, [], {}, set()
    for position, row_id in enumerate(df["_row_id"]):
        value = df.at[position, name_col] if has_names else None
        persons, more, removed, all_others = cells[position]
        if not persons:                                   # vacía, o solo asuntos / referencias de caso
            names.append([value])
            statuses.append("")
            counts.append(1)
            row_marks = ({NOT_A_PERSON} if all_others else set()) | ({MORE_UNNAMED} if more else set())
            if row_marks:
                marks[(row_id, 1)] = row_marks
            continue
        original, status, is_pending = to_text(value), "", False
        if len(persons) == 1 and _several_names_line(persons[0], cedulas[position]):
            parts, suggestion = _glued(persons[0], cedulas[position], has_ids, known, dictionary)
            if parts:                                                        # RF-24
                persons, status = parts, SEPARATED
            else:                                                            # RF-25, RF-26, RF-69
                pending[row_id], status, is_pending = suggestion, NOT_SEPARATED, True
        elif len(persons) > 1 and any(_single_word(person) for person in persons):   # RF-99
            pending[row_id], status, is_pending = _joined_suggestion(persons), NOT_SEPARATED, True
            persons = ["\n".join(persons)]
        elif len(persons) > 1:                                               # RF-22
            status = SEPARATED if has_ids and cedulas[position] == len(persons) else UNCONFIRMED
        decided = False
        # La tabla muestra una celda pendiente con su línea de persona (sin
        # asuntos ni "Y OTROS"): la decisión puede venir con ese texto (T15).
        key = original.strip()
        if key not in by_cell and len(persons) == 1:
            key = persons[0].strip()
        decision = by_cell.get(key)
        if decision is not None:                                             # RF-39, RF-48 (T12)
            parts = None
            if "|" in decision:
                parts = [part.strip() for part in decision.split("|") if part.strip()]
            elif decision == DECISION_ACCEPT and pending.get(row_id):
                parts = pending[row_id].split(" | ")
            elif decision == DECISION_KEEP and (is_pending or len(persons) > 1):
                parts = [original if key == original.strip() else persons[0]]
            if parts:
                applied.add(key)
                pending.pop(row_id, None)
                is_pending, decided, persons = False, len(parts) > 1, parts
                status = "" if len(parts) == 1 else (
                    SEPARATED if has_ids and cedulas[position] == len(parts) else UNCONFIRMED)
        joined = " | ".join(persons)
        if more:
            traces.append(Trace(row_id, original, joined, '"Y OTROS"'))
        if removed:
            traces.append(Trace(row_id, original, joined, "línea que no es de persona"))
        if len(persons) > 1:
            traces.append(Trace(row_id, original, joined, "decisión" if decided else "varios nombres"))
        names.append(persons if (len(persons) > 1 or persons[0] != original) else [value])
        statuses.append(status)
        counts.append(len(persons))
        kept_whole = len(persons) == 1 and persons[0] == original                 # MANTENER: no se quitó nada
        row_marks = (({MORE_UNNAMED} if more else set()) | ({PENDING} if is_pending else set())
                     | ({LINES_REMOVED} if removed and not kept_whole else set()))   # RF-68 (cambio 11)
        for person in range(1, len(persons) + 1):
            if row_marks:
                marks[(row_id, person)] = set(row_marks)

    out = df.iloc[np.repeat(np.arange(len(df)), counts)].reset_index(drop=True)
    if has_names:
        out[name_col] = [name for cell in names for name in cell]
    out["_person"] = [person for count in counts for person in range(1, count + 1)]
    out["ID REGISTRO"] = out["_row_id"] + 1
    out["PERSONA N.º"] = out["_person"]
    out["PERSONAS EN EL REGISTRO"] = np.repeat(counts, counts)
    out["SEPARACIÓN"] = np.repeat(statuses, counts)
    return SeparationResult(out, marks, traces, pending, applied)


def _several_names_line(line: str, cedulas: int) -> bool:
    """
    Una sola línea que cuenta como "celda con varios nombres": más de 5
    palabras sin partículas, 2 cédulas o más, o partes con forma de nombre
    unidas por " Y " o ";" (RF-100, cambio 11).
    """
    return (len(_content(format_key(line, NAMES).split())) > MAX_CONTENT_WORDS or cedulas >= 2
            or _separator_division(line, _STRONG_SEPARATORS) is not None)


def _glued(line: str, cedulas: int, has_ids: bool, known: set[str],
           dictionary: NameDictionary) -> tuple[list[str] | None, str]:
    """
    Nombres pegados en una línea: (las partes, si RF-24 la separa; si no, None)
    y la sugerencia de RF-69 ("" si no hay). RF-24 pide una sola división en
    tantos nombres conocidos como cédulas; sin la columna IDENTIFICACIÓN no
    se aplica (RF-70).
    """
    words = format_key(line, NAMES).split()
    partitions = _known_partitions(words, known)
    if has_ids and cedulas >= 2:
        exact = [partition for partition in partitions if len(partition) == cedulas]
        if len(exact) == 1:
            tokens = _original_tokens(line, words)
            return [" ".join(tokens[start:end]) for start, end in exact[0]], ""
    divisions = [tuple(" ".join(words[start:end]) for start, end in partition) for partition in partitions]
    by_separator = _separator_division(line)
    if by_separator:
        divisions.append(by_separator)
    by_dictionary = dictionary.division(words)
    if by_dictionary:
        divisions.append(tuple(" ".join(words[start:end]) for start, end in by_dictionary))
    chosen = _choose(divisions, cedulas)
    return None, " | ".join(chosen) if chosen else ""
