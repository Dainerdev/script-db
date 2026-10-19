"""Reglas de estandarización por tipo de columna, decisiones, marcas y resumen (spec 002)."""
import datetime
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace

import pandas as pd
from rapidfuzz.distance import Levenshtein

from src.catalog import group, representative, signature
from src.text_keys import COLUMN_TYPES, format_key, obvious_difference, render, similarity, to_text

AUTOMATIC = "AUTOMÁTICO"
REVIEW = "PARA REVISAR"
TO_CONFIRM = "POR CONFIRMAR"
DECIDED = "DECIDIDO"

AUTO_THRESHOLD = 90
SUGGEST_THRESHOLD = 80

FIXED_LISTS = {
    "TIPO DE EXPEDIENTE": ["FÍSICO", "ELECTRÓNICO", "HÍBRIDO", "POR DETERMINAR"],
    "DELEGADA": ["COORDINACIÓN", "1 DELEGADA", "2 DELEGADA", "3 DELEGADA"],
}
_TIPO = "TIPO DE EXPEDIENTE"
_UNDETERMINED = "POR DETERMINAR"
_HYBRID = "HÍBRIDO"

# Columnas cuyo catálogo sale de los datos (grupos de variantes).
_CATALOG_TYPES = {"category", "short_code", "proper_name"}
_NAMES = "NOMBRES_APELLIDOS"
_MAGISTRADO = "MAGISTRADO"

# Definición "No es una persona" (RF-30, RF-57), Decisión #6 del plan:
# palabras enteras, ya sin tildes, sacadas de MAGISTRADO y FUNCIONARIO A
# CARGO del corte del 5 de agosto. El equipo la amplía aquí. No lleva PAZ
# (es apellido); SALA no atrapa SALAS ni CORTE a CORTES.
NON_PERSON_WORDS = frozenset({
    "SALA", "SUBSALA", "SECCION", "SUBSECCION", "CORTE", "COMISION", "COMITE",
    "CONSEJO", "TRIBUNAL", "UNIDAD", "GRUPO", "SECRETARIA", "PRESIDENCIA",
    "DESPACHO", "COMPARECIENTE", "COMPARECIENTES", "PETICIONARIO",
    "PETICIONARIA", "ANONIMO", "PROCESOS", "ARCHIVADO", "ARCHIVADOS",
    "DEVOLUCION", "DETERMINAR", "APLICA", "REFIERE", "INFORMACION", "MEDIDA",
    "CAUTELAR",
})
_NON_PERSON_COLUMNS = {_MAGISTRADO, "FUNCIONARIO A CARGO"}

# Definición "Cédula" de la spec: solo 5 a 15 dígitos.
_CEDULA = re.compile(r"\d{5,15}")

_IDENTIFICATION = "IDENTIFICACIÓN"
# Una línea con una o varias cédulas separadas solo por espacios (RF-35).
_CEDULAS_LINE = re.compile(r"\d{5,15}(?:\s+\d{5,15})*")
# Referencia de caso sobre la clave de formato: "Caso" bien o mal escrito y
# un número donde la letra O vale 0 ("CASO O03", "CSO 006", "CASO001").
_CASE_REFERENCE = re.compile(r"([A-Z]+?)\s?([0-9O]*\d[0-9O]*)")
_CASE_WORD = "CASO"
# RF-33 (y cambio 4): cada familia, por clave de formato, con su escritura.
REPLACEMENT_FAMILIES = {
    "SIN CC": {"SIN CC", "SIN C C", "SIN CEDULA", "SIN IDENTIFICACION"},
    "M.C.": {"M C", "MC"},
    "NO APLICA": {"NO APLICA", "N A"},
}
_INVALID_ID = "identificación inválida"
_ID_FORMAT = "formato de identificación"
_NOT_IN_TABLE = "no está en la tabla revisada"     # RF-90 (cambio 6)
_LONG_NUMBER = re.compile(r"\d{5,}")

# Resultados de la verificación de totales (RF-92), en su orden de precedencia.
EMPTY_TO_UNDETERMINED = "vacía a POR DETERMINAR"
PENDING_RESULT = "pendiente"
CEDULA_AS_IS = "cédula tal cual"
REPLACED = "sustituida"
UNCHANGED = "sin cambio"


@dataclass(frozen=True)
class Outcome:
    """
    Resultado de estandarizar un valor: lo que queda escrito en la celda
    (`final`), el estado para la tabla de estandarización (None si no hay
    nada que registrar: la celda ya estaba bien o está vacía), el motivo y,
    si queda pendiente, la sugerencia con su similitud. `not_a_person`
    marca la fila "no es una persona" (RF-30, RF-57), aparte del estado.
    """
    final: str
    state: str | None = None
    motive: str = ""
    suggestion: str = ""
    similarity: float | None = None
    not_a_person: bool = False

    @property
    def pending(self) -> bool:
        """Solo PARA REVISAR es pendiente: POR CONFIRMAR no se colorea ni se cuenta (RF-56)."""
        return self.state == REVIEW


@dataclass(frozen=True)
class ColumnClassification:
    """
    Resultado de una columna con catálogo sacado de los datos: el Outcome
    de cada valor original y, en SALA, cada código POR CONFIRMAR (RF-16),
    que va a la tabla aparte porque no cambia ninguna celda.
    """
    outcomes: dict
    to_confirm: dict[str, Outcome] = field(default_factory=dict)


def empty_outcome(column) -> Outcome:
    """
    Celda vacía (o con solo espacios o signos): POR DETERMINAR en todas las
    columnas, sin dejarla pendiente (RF-18; RF-21 desde el cambio 6, antes
    quedaba vacía fuera de TIPO DE EXPEDIENTE). Se registra con el motivo
    "vacío" (RF-41).
    """
    return Outcome(_UNDETERMINED, AUTOMATIC, "vacío")


def _unchanged_or_format(value, final: str) -> Outcome:
    if to_text(value) == final:
        return Outcome(final)
    return Outcome(final, AUTOMATIC, "formato")


def classify_fixed_list(value, column) -> Outcome:
    """
    TIPO DE EXPEDIENTE y DELEGADA, cuyo catálogo es una lista fija (RF-3,
    RF-4), en este orden:
    1. vacío → POR DETERMINAR (RF-18, RF-21);
    2. igual a un valor de la lista salvo formato → ese valor (RF-9);
    3. similitud de 90 o más con un valor de la lista con los mismos números
       y la misma negación → ese valor (RF-10, RF-17, RF-82);
    4. TIPO DE EXPEDIENTE: FÍSICO y ELECTRÓNICO a la vez → HÍBRIDO (RF-66); el
       resto → POR DETERMINAR, con el original en la tabla (RF-19);
    5. DELEGADA: pendiente con el valor original; se sugiere el de la lista
       más parecido si tiene similitud de 80 o más (RF-81). Solo se sugiere
       un valor con los mismos números: "4 DELEGADA" se parece 90 a "1
       DELEGADA", pero es otra dependencia (misma regla que RF-17). Ante un
       empate de similitud, el primero de la lista.
    """
    key = format_key(value, column)
    if not key:
        return empty_outcome(column)

    items = FIXED_LISTS[column]
    for item in items:
        if format_key(item, column) == key:
            return _unchanged_or_format(value, item)

    column_type = COLUMN_TYPES[column]
    key_signature = signature(key, column_type)
    comparable = [
        (similarity(key, format_key(item, column)), item)
        for item in items
        if signature(format_key(item, column), column_type) == key_signature
    ]
    best_score, best_item = max(comparable, key=lambda scored: scored[0], default=(0, ""))
    if best_score >= AUTO_THRESHOLD:
        return Outcome(best_item, AUTOMATIC, "error de tipeo", similarity=best_score)

    if column == _TIPO:
        if {"FISICO", "ELECTRONICO"} <= set(key.split()):
            return Outcome(_HYBRID, AUTOMATIC, "dos tipos en una celda")
        return Outcome(_UNDETERMINED, AUTOMATIC, "otra categoría")

    original = to_text(value)
    if best_score >= SUGGEST_THRESHOLD:
        return Outcome(original, REVIEW, "similitud 80–89", best_item, best_score)
    return Outcome(original, REVIEW, "otra categoría")


def is_other_category(value, column) -> bool:
    """
    Definición "valor de otra categoría" de la spec 002: una fecha en una
    columna que no es de fechas (ninguna de las estandarizadas lo es);
    dígitos en una columna de nombre propio; solo dígitos en una columna de
    categoría o de código corto ("0", "007-2025", 44317 — el número que
    Excel guarda para una fecha). Los signos y espacios no cuentan: "15/03/2021"
    escrito como texto también es una fecha.
    """
    key = format_key(value, column)
    if not key:
        return False
    if isinstance(value, datetime.date):
        return True
    column_type = COLUMN_TYPES.get(column)
    if column_type == "proper_name":
        return any(char.isdigit() for char in key)
    if column_type in ("category", "short_code"):
        return key.replace(" ", "").isdigit()
    return False


def is_not_a_person(value, column) -> bool:
    """
    Definición "No es una persona" (MAGISTRADO y FUNCIONARIO A CARGO): el
    valor tiene alguna palabra entera de NON_PERSON_WORDS. En
    NOMBRES_APELLIDOS lo que no es persona son los asuntos (RF-28), que se
    ven al separar comparecientes.
    """
    if column not in _NON_PERSON_COLUMNS:
        return False
    return not NON_PERSON_WORDS.isdisjoint(format_key(value, column).split())


def _is_person(key: str) -> bool:
    return NON_PERSON_WORDS.isdisjoint(key.split()) and not any(char.isdigit() for char in key)


def _several_magistrates(keys) -> set[str]:
    """
    RF-31: claves de MAGISTRADO que contienen dos o más nombres que aparecen
    solos en otras filas, sin solaparse ("ANA MARIA PEREZ" y "MARIA PEREZ
    GOMEZ" dentro de "ANA MARIA PEREZ GOMEZ" son una sola persona). Un nombre
    conocido tiene al menos dos palabras, y la Ñ se compara como N: la misma
    magistrada aparece como PEÑALOZA y como PENALOZA.
    """
    people = [key for key in keys if _is_person(key)]
    known = {key.replace("Ñ", "N") for key in people if len(key.split()) >= 2}
    several = set()
    for key in people:
        words = key.replace("Ñ", "N").split()
        spans = [
            (start, end)
            for start in range(len(words))
            for end in range(start + 2, len(words) + 1)
            if (start, end) != (0, len(words)) and " ".join(words[start:end]) in known
        ]
        names, last_end = 0, -1
        for start, end in sorted(spans, key=lambda span: span[1]):
            if start >= last_end:
                names, last_end = names + 1, end
        if names >= 2:
            several.add(key)
    return several


def _cedulas_by_key(cedulas, column) -> dict[str, Counter]:
    """
    Filas por cédula de cada nombre (clave de formato). Solo cuenta una
    identificación que es una sola cédula: un grupo de varias (el que lleva
    cada persona separada de una misma celda, RF-22) haría parecer que dos
    nombres comparten cédula (RF-94).
    """
    by_key = defaultdict(Counter)
    for name, ids in (cedulas or {}).items():
        key = format_key(name, column)
        for identification, rows in ids.items():
            text = to_text(identification).strip()
            if key and _CEDULA.fullmatch(text):
                by_key[key][text] += rows
    return by_key


def _classify_variant(value, column, catalog_value: str, confirmed_by_cedula=False,
                      cedulas_disagree=False) -> Outcome:
    """
    Una variante frente al valor del catálogo de su grupo (cambio 3: la
    similitud se mide contra ese valor, no contra la apertura del grupo).
    En nombres propios nada se reemplaza solo salvo el formato, la cédula
    compartida (RF-13) y lo muy obvio (RF-85): un 95 puede ser otra persona
    (MARCELA / MARCELO no es un tipeo leve). Lo muy obvio no se une si en
    NOMBRES_APELLIDOS las cédulas de los dos no tienen ninguna en común.
    """
    key = format_key(value, column)
    catalog_key = format_key(catalog_value, column)
    if key == catalog_key:
        return _unchanged_or_format(value, catalog_value)                  # RF-9
    score = similarity(key, catalog_key)
    is_name = COLUMN_TYPES[column] == "proper_name"
    obvious = obvious_difference(key, catalog_key) is not None and not cedulas_disagree
    if (score >= AUTO_THRESHOLD and not is_name) or confirmed_by_cedula or obvious:
        return Outcome(catalog_value, AUTOMATIC, "error de tipeo", similarity=score)  # RF-10, RF-13, RF-85
    if score >= AUTO_THRESHOLD:
        motive = "error de tipeo"                                           # RF-12
    elif score >= SUGGEST_THRESHOLD:
        motive = "similitud 80–89"                                          # RF-11
    else:
        motive = "similitud menor que 80"                                   # RF-84
    return Outcome(to_text(value), REVIEW, motive, catalog_value, score)


def _other_name_with_same_cedula(key, ids_by_key, keys_by_cedula, group_of) -> str | None:
    """
    RF-65: si todas las filas con cédula de este nombre tienen la misma, y
    esa cédula aparece en más filas con otro nombre de similitud menor que
    80, ese otro nombre (el de más filas con ella; empate: alfabético). Solo
    cuenta un nombre de otro grupo: dentro del mismo grupo, la variante ya
    queda pendiente o se corrige frente a su valor del catálogo.
    """
    ids = ids_by_key.get(key)
    if not ids or len(ids) != 1:
        return None
    ((cedula, rows),) = ids.items()
    others = [
        (other_rows, other)
        for other, other_rows in keys_by_cedula[cedula].items()
        if other_rows > rows
        and group_of.get(other) not in (None, group_of[key])
        and similarity(key, other) < SUGGEST_THRESHOLD
    ]
    if not others:
        return None
    return min(others, key=lambda other: (-other[0], other[1]))[1]


def classify_catalog_column(value_counts, column, cedulas=None) -> ColumnClassification:
    """
    Columnas cuyo catálogo sale de los datos: categorías (SOLICITUD,
    DECISIÓN, PERTENECE), SALA y nombres propios (NOMBRES_APELLIDOS,
    MAGISTRADO, FUNCIONARIO A CARGO). Recibe cada valor original con su
    cantidad de filas (un dict o el `value_counts()` de pandas) y, para
    NOMBRES_APELLIDOS, las cédulas de cada valor ({valor: {cédula: filas}}).
    Clasifica cada valor:
    1. vacío → POR DETERMINAR, sin dejarlo pendiente (RF-21, cambio 6);
    2. de otra categoría → pendiente con su texto original, sin sugerencia
       (RF-20); no entra a los grupos, así no llega al catálogo;
    3. en MAGISTRADO, varios magistrados en la celda → pendiente, sin
       separarla ni sugerir (RF-31); tampoco entra a los grupos;
    4. el resto se agrupa (catalog.group) y se compara con el valor del
       catálogo de su grupo (catalog.representative): solo formato → ese
       valor (RF-9); 90 o más → ese valor en categorías (RF-10), pendiente
       en nombres (RF-12); 80 a 89 → pendiente con sugerencia (RF-11);
       menos de 80 → pendiente con sugerencia (RF-84); en
       NOMBRES_APELLIDOS, una variante cuyas cédulas aparecen todas con el
       valor del catálogo → ese valor (RF-13; solo cuentan las filas cuya
       identificación es una sola cédula, RF-94). El que abre su propio grupo
       es su propio valor del catálogo (RF-14);
    5. en NOMBRES_APELLIDOS, un nombre que no quedó pendiente y comparte su
       única cédula con otro nombre muy distinto de más filas → pendiente
       con ese nombre como sugerencia (RF-65).
    En SALA cada código es su propio grupo (RF-15) y queda POR CONFIRMAR
    (RF-16), sin contar como pendiente (RF-56). En MAGISTRADO y FUNCIONARIO
    A CARGO, lo que no es una persona se estandariza igual y lleva la marca
    (RF-30, RF-57).
    """
    column_type = COLUMN_TYPES.get(column)
    if column_type not in _CATALOG_TYPES:
        raise ValueError(f"{column} no es una columna de categoría, código corto ni nombre propio")

    several = set()
    if column == _MAGISTRADO:
        several = _several_magistrates({format_key(value, column) for value in value_counts.keys()})

    outcomes = {}
    grouped = {}
    for value, rows in value_counts.items():
        key = format_key(value, column)
        if not key:
            outcomes[value] = empty_outcome(column)
        elif is_other_category(value, column):
            outcomes[value] = Outcome(_UNDETERMINED, AUTOMATIC, "otra categoría")   # RF-20 (cambio 5)
        elif key in several:
            outcomes[value] = Outcome(to_text(value), REVIEW, "varios magistrados")
        else:
            grouped[value] = rows

    group_of = group(grouped, column)
    variants_by_opener = defaultdict(dict)
    for value, rows in grouped.items():
        variants_by_opener[group_of[format_key(value, column)]][value] = rows

    ids_by_key = _cedulas_by_key(cedulas, column) if column == _NAMES else {}
    catalog_by_opener = {}
    to_confirm = {}
    for opener, variants in variants_by_opener.items():
        catalog_value = representative(variants, column)
        catalog_by_opener[opener] = catalog_value
        catalog_ids = set(ids_by_key.get(format_key(catalog_value, column), ()))
        for value in variants:
            ids = set(ids_by_key.get(format_key(value, column), ()))
            confirmed = bool(ids) and ids <= catalog_ids
            disagree = bool(ids) and bool(catalog_ids) and not ids & catalog_ids
            outcomes[value] = _classify_variant(value, column, catalog_value, confirmed, disagree)
        if column_type == "short_code":
            to_confirm[catalog_value] = Outcome(catalog_value, TO_CONFIRM, "confirmar código de SALA")

    keys_by_cedula = defaultdict(Counter)
    for key, ids in ids_by_key.items():
        for cedula, rows in ids.items():
            keys_by_cedula[cedula][key] += rows
    for value in grouped:
        if outcomes[value].pending or not ids_by_key:
            continue
        key = format_key(value, column)
        other = _other_name_with_same_cedula(key, ids_by_key, keys_by_cedula, group_of)
        if other is not None:
            outcomes[value] = Outcome(
                to_text(value), REVIEW, "misma cédula con nombres distintos",
                catalog_by_opener[group_of[other]], similarity(key, other),
            )

    if column in _NON_PERSON_COLUMNS:
        for value, outcome in outcomes.items():
            if is_not_a_person(value, column):
                outcomes[value] = replace(outcome, not_a_person=True)

    return ColumnClassification(outcomes, to_confirm)


def is_case_reference(value) -> bool:
    """
    Definición "Referencia de caso": solo "Caso" y un número, bien o mal
    escrito ("Caso 003", "Caso O03", "Cso 006", "Caso001"). La usan
    IDENTIFICACIÓN (RF-32) y la separación de comparecientes (RF-28, RF-68).
    """
    reference = _CASE_REFERENCE.fullmatch(format_key(value, _IDENTIFICATION))
    return bool(reference) and Levenshtein.distance(reference[1], _CASE_WORD) <= 1


def _identification_line(line: str) -> str | None:
    """
    Escritura final de una línea de IDENTIFICACIÓN, o None si es inválida
    (RF-34): error de Excel, letras y números mezclados, números de menos de
    5 o más de 15 dígitos, más de un caso, o solo letras sin ser una familia.
    """
    text = line.strip()
    if text.startswith("#"):                        # "#¡VALOR!", "#N/A": antes que la familia N/A
        return None
    if _CEDULAS_LINE.fullmatch(text):               # RF-35
        return text
    key = format_key(text, _IDENTIFICATION)
    reference = _CASE_REFERENCE.fullmatch(key)
    if reference and Levenshtein.distance(reference[1], _CASE_WORD) <= 1:   # RF-32
        number = int(reference[2].replace("O", "0"))
        return f"{_CASE_WORD} {number:03d}"
    for final, members in REPLACEMENT_FAMILIES.items():                     # RF-33
        if key in members:
            return final
    return None


def classify_identification(value) -> Outcome:
    """
    IDENTIFICACIÓN, que no se agrupa por parecido (dos cédulas parecidas son
    dos personas). Cada línea de la celda se escribe por su regla:
    referencia de caso → "CASO " y el número con al menos tres dígitos
    (RF-32); familia de reemplazo → su escritura (RF-33); cédulas → tal
    cual, sin espacios alrededor ni ".0" (RF-35). Si alguna línea no es
    nada de eso, la celda queda pendiente sin sugerencia (RF-34), salvo que
    ninguna línea valga y todas sean solo letras o errores de Excel: eso no
    es una identificación y queda POR DETERMINAR (cambio 5). Motivo
    (cambio 4): "formato" si solo difiere en formato ("Caso 003"), si no
    "formato de identificación" ("Caso O03", "N/A").
    """
    original = to_text(value)
    if not format_key(value, _IDENTIFICATION):
        return empty_outcome(_IDENTIFICATION)
    lines = [line for line in original.split("\n") if line.strip()]
    finals = [_identification_line(line) for line in lines]
    if None in finals:
        not_an_id = all(
            final is None and (line.strip().startswith("#") or not any(c.isdigit() for c in line))
            for line, final in zip(lines, finals)
        )
        if not_an_id:
            return Outcome(_UNDETERMINED, AUTOMATIC, "otra categoría")         # RF-34 (cambio 5)
        return Outcome(original, REVIEW, _INVALID_ID)
    final = "\n".join(finals)
    if final == original:
        return Outcome(final)
    if format_key(final, _IDENTIFICATION) == format_key(value, _IDENTIFICATION):
        return Outcome(final, AUTOMATIC, "formato")
    return Outcome(final, AUTOMATIC, _ID_FORMAT)


# ---------------------------------------------------------------------------
# Cambio 6: tabla de parámetros revisados, columnas _ORIGINAL y totales
# ---------------------------------------------------------------------------

class TotalsMismatchError(Exception):
    """La verificación de totales de RF-92 no cuadra: no se guarda el resultado."""


def has_long_number(text) -> bool:
    """Si el texto trae algún número de 5 o más dígitos, sin contar los puntos de miles (RF-91)."""
    return bool(_LONG_NUMBER.search(to_text(text).replace(".", "")))


@dataclass
class ReviewedTable:
    """
    Tabla de parámetros revisados (definición del cambio 6): cada fila dice
    qué valor final lleva un valor original de una columna. `rows` guarda
    las filas tal como venían (para copiarlas completas, RF-96); `finals`,
    solo las que se pueden aplicar. No se aplican, y se listan (RF-89), el
    mismo original con dos finales distintos (`conflicts`) y un final fuera
    de la lista de una columna de lista fija (`invalid`). El original se
    guarda sin espacios en los extremos ni ".0" (RF-35, RF-88); el final,
    exacto (RF-93).
    """
    rows: list = field(default_factory=list)
    finals: dict = field(default_factory=dict)
    conflicts: list = field(default_factory=list)
    invalid: list = field(default_factory=list)
    columns: set = field(default_factory=set)      # se calcula una vez: se consulta por cada celda

    @classmethod
    def from_rows(cls, rows) -> "ReviewedTable":
        table = cls()
        finals_of = defaultdict(list)
        for column, original, final in rows:
            row = (to_text(column).strip(), to_text(original).strip(), to_text(final))
            table.rows.append(row)
            table.columns.add(row[0])
            if row[2] not in finals_of[row[:2]]:
                finals_of[row[:2]].append(row[2])
        for pair, finals in finals_of.items():
            column = pair[0]
            if len(finals) > 1:
                table.conflicts.append(pair)
            elif column in FIXED_LISTS and finals[0] not in FIXED_LISTS[column]:
                table.invalid.append(pair)
            else:
                table.finals[pair] = finals[0]
        return table

    def lookup(self, column, original_text: str) -> str | None:
        """Valor final de un original (texto sin espacios en los extremos), o None."""
        return self.finals.get((column, original_text))

    def problems(self) -> list[str]:
        """RF-89: las filas que no se aplican, con el texto que va al resumen (como RF-48)."""
        listed = [f"Tabla revisada · {column} · «{original}»: dos valores finales distintos; no se aplicó."
                  for column, original in self.conflicts]
        finals = {row[:2]: row[2] for row in self.rows}
        listed += [f"Tabla revisada · {column} · «{original}»: el valor final «{finals[(column, original)]}» "
                   "no está en la lista de la columna; no se aplicó." for column, original in self.invalid]
        return listed

    def same_format_final(self, column, original) -> str | None:
        """RF-90: el final de los originales que solo se diferencian de este en formato, si es uno solo."""
        if not hasattr(self, "_by_key"):
            by_key = defaultdict(set)
            for (col, text), final in self.finals.items():
                by_key[(col, format_key(text, col))].add(final)
            self._by_key = by_key
        finals = self._by_key.get((column, format_key(original, column)), set())
        return next(iter(finals)) if len(finals) == 1 else None


def apply_reviewed_table(original, automatic: Outcome, column, table: ReviewedTable | None,
                         current=None) -> Outcome:
    """
    Resultado de una celda con la tabla de parámetros revisados (RF-88 a
    RF-93). `original` es el valor crudo de la celda (el de su columna
    _ORIGINAL: así se armó la tabla); `automatic`, lo que da la regla
    automática; `current`, el valor ya limpio, que conserva una celda que no
    está en la tabla (si no se da, el original).
    - Columna fuera de la tabla, sin tabla o celda vacía → la regla.
    - En la tabla → su valor final exacto, DECIDIDO, motivo "decisión"
      (RF-88, RF-93); en IDENTIFICACIÓN, si ese final trae números de 5
      dígitos o más, el original queda tal cual (RF-91).
    - Fuera de la tabla, una o varias cédulas → la regla (RF-35); lo demás
      queda como estaba y pendiente, con la sugerencia de RF-90.
    """
    if table is None or column not in table.columns or not format_key(original, column):
        return automatic
    text = to_text(original).strip()
    final = table.lookup(column, text)
    if final is not None:
        if column == _IDENTIFICATION and has_long_number(final):                    # RF-91
            return _unchanged_or_format(original, text)
        if final == to_text(original):
            return Outcome(final)
        return Outcome(final, DECIDED, "decisión")                                  # RF-88, RF-93
    if column == _IDENTIFICATION and _CEDULAS_LINE.fullmatch(text):                 # RF-35
        return automatic
    suggestion = table.same_format_final(column, original)                          # RF-90
    if suggestion is None:
        suggestion = automatic.suggestion if automatic.pending else automatic.final
    return Outcome(to_text(original if current is None else current), REVIEW, _NOT_IN_TABLE, suggestion)


def canonical_column(name) -> str | None:
    """
    Nombre de la columna estandarizada a la que corresponde un encabezado, o
    None. Reconoce TIPO DE EXPEDIENTE con texto extra en el encabezado (RF-54).
    """
    text = to_text(name).strip()
    if text in COLUMN_TYPES:
        return text
    if text.upper().startswith(_TIPO) and not text.endswith("_ORIGINAL"):
        return _TIPO
    return None


def add_original_columns(df):
    """
    RF-87: junto a cada columna estandarizada, otra con su nombre canónico
    más "_ORIGINAL" y el valor de cada celda tal como venía, antes de
    cualquier limpieza. Si ya existe, no se repite. No cambia `df`.
    """
    out = df.copy()
    for name in list(df.columns):
        canonical = canonical_column(name)
        if canonical is None or f"{canonical}_ORIGINAL" in out.columns:
            continue
        out.insert(out.columns.get_loc(name) + 1, f"{canonical}_ORIGINAL", df[name])
    return out


def result_category(outcome: Outcome, column) -> str:
    """Resultado de una fila para RF-92: el primero que le corresponde en el orden de la spec."""
    if outcome.motive == "vacío":
        return EMPTY_TO_UNDETERMINED
    if outcome.pending:
        return PENDING_RESULT
    if column == _IDENTIFICATION and outcome.motive in ("", "formato") and has_long_number(outcome.final):
        return CEDULA_AS_IS
    if outcome.state in (AUTOMATIC, DECIDED) and outcome.motive != "formato":
        return REPLACED
    return UNCHANGED


def verify_totals(rows_by_column: dict, total: int) -> dict[str, Counter]:
    """
    RF-92: por cada columna estandarizada salvo NOMBRES_APELLIDOS, cuántas
    filas quedaron en cada resultado. Recibe, por columna, un par (valor
    original, Outcome) por fila, antes de separar comparecientes. Si una
    columna no suma `total`, lanza TotalsMismatchError con un mensaje claro.
    """
    totals = {}
    for column, rows in rows_by_column.items():
        if column == _NAMES:
            continue
        counts = Counter(result_category(outcome, column) for _, outcome in rows)
        if counts.total() != total:
            raise TotalsMismatchError(
                f"La verificación de totales no cuadra en la columna {column}: se contaron "
                f"{counts.total()} filas y el archivo tiene {total}. No se guardó el resultado.")
        totals[column] = counts
    return totals


# ---------------------------------------------------------------------------
# T11: estandarizar las columnas de un DataFrame
# ---------------------------------------------------------------------------

MARK_PENDING = "pendiente de revisión"          # marcas de "Observación estandarización" (RF-78)
MARK_NOT_A_PERSON = "no es una persona"
OBSERVATION = "Observación estandarización"
SUMMARY_UNCHANGED = "SIN CAMBIO"               # resumen: valor que no cambió (RF-43)
_OTHER_CATEGORY = "otra categoría"
_SALA_CODE = "confirmar código de SALA"
DECISION_ACCEPT, DECISION_KEEP = "ACEPTAR", "MANTENER"     # RF-39, RF-72
_DECISION = "decisión"
_CORRECTION = "corrección de catálogo"
SEVERAL_NAMES = "celda con varios nombres"     # motivo de una celda SIN SEPARAR (RF-25, RF-26)
_NOT_SEPARATED = "SIN SEPARAR"


@dataclass
class Decisions:
    """
    Decisiones cargadas de un Excel de revisión (plan, T12): filas (columna,
    valor original, texto de "Decisión") y (columna, valor del catálogo,
    texto de "Corregir a"). Son listas para poder ver un par con dos
    decisiones distintas (RF-48).
    """
    table: list = field(default_factory=list)
    catalog: list = field(default_factory=list)


@dataclass
class TableEntry:
    """Fila de la tabla de estandarización (RF-37): un par (columna, valor original) que cambió o quedó pendiente."""
    column: str
    original: str
    final: str            # valor final, o la sugerencia si quedó PARA REVISAR ("" si no hay)
    similarity: float | None
    motive: str
    state: str
    row_ids: list = field(default_factory=list)
    decision: str | None = None


@dataclass
class StandardizationResult:
    """Resultado de `standardize_parameters` (plan, modelo de datos; T12 suma las decisiones)."""
    df: object
    entries: list
    catalogs: dict
    summary: dict
    totals: dict
    missing_columns: list
    unmatched_decisions: int = 0                    # RF-77
    invalid_decisions: list = field(default_factory=list)   # RF-48
    loaded_decisions: object = None                 # se copian al nuevo Excel de revisión (RF-46)


def _value_key(value) -> tuple[str, str]:
    """Clave para agrupar valores crudos iguales (un NaN no es igual a otro NaN)."""
    return type(value).__name__, to_text(value)


def _automatic_outcomes(column, values, included, ids) -> tuple[dict, dict]:
    """Lo que dicen las reglas para cada valor distinto de la columna: {clave: Outcome} y los códigos POR CONFIRMAR."""
    kind = COLUMN_TYPES[column]
    distinct = {}
    for value, keep in zip(values, included):
        if keep:
            distinct.setdefault(_value_key(value), value)
    if kind == "fixed_list":
        return {key: classify_fixed_list(value, column) for key, value in distinct.items()}, {}
    if kind == "identification":
        return {key: classify_identification(value) for key, value in distinct.items()}, {}
    counts, cedulas = Counter(), defaultdict(Counter)
    for value, keep, identification in zip(values, included, ids):
        if keep:
            representative_value = distinct[_value_key(value)]
            counts[representative_value] += 1
            if column == _NAMES and identification is not None:
                cedulas[representative_value][to_text(identification).strip()] += 1
    classification = classify_catalog_column(counts, column, cedulas if column == _NAMES else None)
    outcomes = {_value_key(value): outcome for value, outcome in classification.outcomes.items()}
    return outcomes, classification.to_confirm


def _registered(outcome: Outcome) -> bool:
    """Si el valor va a la tabla de estandarización: toda sustitución que no es solo formato y todo pendiente (RF-37, RF-41)."""
    return outcome.state in (REVIEW, DECIDED) or (outcome.state == AUTOMATIC and outcome.motive != "formato")


def _table_entries(column, originals, outcomes, row_ids, awaiting, decided_by=None) -> list:
    grouped = {}
    decided_by = decided_by or [None] * len(outcomes)
    for original, outcome, row_id, decision in zip(originals, outcomes, row_ids, decided_by):
        if not _registered(outcome):
            continue
        shown = outcome.suggestion if outcome.pending else outcome.final
        key = (to_text(original).strip(), shown, outcome.state, outcome.motive, decision)
        if key not in grouped:
            grouped[key] = TableEntry(column, key[0], shown, outcome.similarity, outcome.motive, outcome.state,
                                      decision=decision)
        grouped[key].row_ids.append(row_id)
    entries = list(grouped.values())
    for code in sorted(awaiting):                                                    # RF-16
        rows = [row_id for outcome, row_id in zip(outcomes, row_ids) if outcome.final == code and not outcome.pending]
        entries.append(TableEntry(column, code, code, None, _SALA_CODE, TO_CONFIRM, rows))
    return entries


def _catalog(outcomes, included):
    """RF-42: cada valor final con su cantidad de filas, sin los pendientes ni lo que no entra al catálogo."""
    counts = Counter(outcome.final for outcome, keep in zip(outcomes, included) if keep and not outcome.pending)
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return pd.DataFrame(ordered, columns=["Valor", "Filas"])


def _summary(originals, outcomes, awaiting) -> dict:
    """
    RF-43: por estado, cuántos valores distintos y cuántas filas. Cada valor
    cuenta en un solo estado (el de su primera fila); cada fila, en el suyo,
    así las filas cuadran con la verificación de RF-92 aunque dos escrituras
    del mismo valor ("1 DELEGADA" y "1 DELEGADA ") terminen distinto. Los de
    otra categoría se muestran aparte. En SALA, un valor cuyo código espera
    confirmación cuenta como POR CONFIRMAR (RF-16, RF-56).
    """
    seen, values, rows = set(), Counter(), Counter()
    other_values, other_rows = set(), 0
    for original, outcome in zip(originals, outcomes):
        key = to_text(original).strip()
        state = outcome.state or SUMMARY_UNCHANGED
        if outcome.final in awaiting and outcome.motive in ("", "formato") and not outcome.pending:
            state = TO_CONFIRM
        rows[state] += 1
        if key not in seen:
            seen.add(key)
            values[state] += 1
        if outcome.motive == _OTHER_CATEGORY:
            other_values.add(key)
            other_rows += 1
    return {"estados": {state: (values[state], rows[state]) for state in rows},
            _OTHER_CATEGORY: (len(other_values), other_rows)}


def _normalized_decision(text) -> str:
    """ACEPTAR y MANTENER sin importar mayúsculas ni espacios (RF-72); otro texto, sin espacios en los extremos."""
    text = to_text(text).strip()
    return text.upper() if text.upper() in (DECISION_ACCEPT, DECISION_KEEP) else text


def _valid_decisions(rows, column, kind, problems) -> dict:
    """
    Decisiones (o correcciones) de una columna que se pueden aplicar:
    {valor: texto}. No se aplican, y se listan (RF-48), un par con dos
    decisiones distintas y un valor fuera de la lista en una columna de
    lista fija. En NOMBRES_APELLIDOS quedan fuera las que separan nombres
    (" | "): las aplica `comparecientes.separate`.
    """
    texts, first = defaultdict(set), {}
    for row_column, value, text in rows:
        if to_text(row_column).strip() != column or not to_text(text).strip():
            continue
        if column == _NAMES and "|" in to_text(text):
            continue
        key = to_text(value).strip()
        texts[key].add(_normalized_decision(text))
        first.setdefault(key, to_text(text))
    valid = {}
    for key, distinct in texts.items():
        word = next(iter(distinct))
        if len(distinct) > 1:
            problems.append(f"{column} · «{key}»: dos {kind} distintas; no se aplicó ninguna.")
        elif (column in FIXED_LISTS and word not in (DECISION_ACCEPT, DECISION_KEEP)
              and render(word, column) not in FIXED_LISTS[column]):
            problems.append(f"{column} · «{key}»: «{word}» no está en la lista de la columna; no se aplicó.")
        else:
            valid[key] = first[key]
    return valid


def _decided(text, outcome: Outcome, current, column) -> Outcome | None:
    """
    Resultado de una decisión (RF-45): ACEPTAR usa la sugerencia (None si no
    hay: no se puede aplicar); MANTENER deja el valor como estaba, también
    para deshacer una sustitución automática; otro texto es el valor final,
    con la ortografía de su columna (RF-74).
    """
    word = _normalized_decision(text)
    if word == DECISION_ACCEPT:
        if outcome.pending:
            return Outcome(outcome.suggestion, DECIDED, _DECISION) if outcome.suggestion else None
        return outcome
    if word == DECISION_KEEP:
        return Outcome(to_text(current), DECIDED, _DECISION)
    return Outcome(render(word, column), DECIDED, _DECISION)


def apply_overrides(column, originals, currents, outcomes, decisions: Decisions, awaiting, problems):
    """
    Decisiones de la tabla de estandarización y correcciones de catálogo de
    una columna, con la prioridad de la Decisión #12: decisión > corrección
    de catálogo > tabla revisada > regla (RF-45, RF-58, RF-89). En SALA, una
    decisión sobre un código POR CONFIRMAR vale para todas sus filas:
    ACEPTAR o MANTENER lo confirman, otro texto lo vuelve variante (RF-73).
    Una corrección alcanza al valor del catálogo y a sus variantes, también
    las pendientes (RF-58). Devuelve los resultados, el texto de la decisión
    de cada fila (o None), los códigos que siguen POR CONFIRMAR y cuántas
    decisiones no coincidieron con ningún valor (RF-77).
    """
    by_row = _valid_decisions(decisions.table, column, "decisiones", problems)
    corrections = _valid_decisions(decisions.catalog, column, "correcciones", problems)
    by_code = {key: by_row.pop(key) for key in list(by_row) if key in awaiting}
    result, decided_by, matched, matched_corrections, failed = [], [], set(), set(), set()
    for original, current, outcome in zip(originals, currents, outcomes):
        key, text = to_text(original).strip(), None
        if key in by_row:
            matched.add(key)
            decided = _decided(by_row[key], outcome, current, column)
            if decided is None:
                if key not in failed:
                    failed.add(key)
                    problems.append(f"{column} · «{key}»: ACEPTAR, pero no hay sugerencia; no se aplicó.")
            else:
                outcome, text = decided, by_row[key]
        elif not outcome.pending and outcome.final in by_code:                       # RF-73
            matched.add(outcome.final)
            text = by_code[outcome.final]
            word = _normalized_decision(text)
            if word not in (DECISION_ACCEPT, DECISION_KEEP):
                outcome = Outcome(render(word, column), DECIDED, _DECISION)
        else:
            value = outcome.suggestion if outcome.pending else outcome.final
            if value in corrections:                                                  # RF-58
                matched_corrections.add(value)
                outcome = Outcome(render(_normalized_decision(corrections[value]), column), DECIDED, _CORRECTION)
        result.append(outcome)
        decided_by.append(text)
    unmatched = (len(set(by_row) - matched) + len(set(by_code) - matched)
                 + len(set(corrections) - matched_corrections))
    return result, decided_by, set(awaiting) - set(by_code), unmatched


def _included_rows(column, marks, separation) -> list:
    """
    Filas que se clasifican y entran al catálogo. En NOMBRES_APELLIDOS no
    entran las marcadas "no es una persona" (RF-28) ni las que quedaron SIN
    SEPARAR (RF-25): reciben solo el formato de la columna.
    """
    if column != _NAMES:
        return [True] * len(marks)
    return [MARK_NOT_A_PERSON not in row_marks and status != _NOT_SEPARATED
            for row_marks, status in zip(marks, separation)]


def standardize_parameters(df, table=None, columns=None, decisions: Decisions | None = None,
                           check_columns: bool = True, separation_suggestions: dict | None = None,
                           before_column=None) -> StandardizationResult:
    """
    Estandariza las columnas estandarizadas presentes (RF-1, RF-53; TIPO DE
    EXPEDIENTE con texto extra en el encabezado, RF-54) y devuelve el
    DataFrame, las entradas de la tabla de estandarización (RF-37, RF-41),
    los catálogos (RF-2, RF-42), el resumen por estado (RF-43) y la
    verificación de totales (RF-92). `columns` limita las columnas: con el
    orden del cambio 6 se llama una vez sin NOMBRES_APELLIDOS, antes de
    separar comparecientes, y otra solo con NOMBRES_APELLIDOS, después.
    `table` es la tabla de parámetros revisados (RF-88 a RF-93), que se
    busca con la columna _ORIGINAL si existe. `decisions` son las decisiones
    y correcciones cargadas (T12, `apply_overrides`); `check_columns` lista
    las de una columna inexistente (se apaga en la segunda pasada, para no
    listarlas dos veces). Las marcas y los pendientes de cada fila se suman
    a las columnas internas `_marks` y `_pending`. Una celda de nombres SIN
    SEPARAR queda PARA REVISAR con la sugerencia de `separation_suggestions`
    ({_row_id: partes con " | "}, de `comparecientes.separate`; RF-25,
    RF-26, RF-69). `before_column(columna)` se llama antes de cada columna:
    el pipeline revisa ahí si el funcionario canceló (RF-55).
    """
    df = df.reset_index(drop=True).copy()
    n = len(df)
    if "_row_id" not in df.columns:
        df["_row_id"] = range(n)
    marks = [list(row) for row in df["_marks"]] if "_marks" in df.columns else [[] for _ in range(n)]
    pending = [list(row) for row in df["_pending"]] if "_pending" in df.columns else [[] for _ in range(n)]
    separation = list(df["SEPARACIÓN"]) if "SEPARACIÓN" in df.columns else [""] * n
    ids = list(df[_IDENTIFICATION]) if _IDENTIFICATION in df.columns else [None] * n
    row_ids = list(df["_row_id"])

    present = {}
    for name in df.columns:
        canonical = canonical_column(name)
        if canonical is not None and canonical not in present:
            present[canonical] = name
    wanted = [column for column in COLUMN_TYPES if columns is None or column in columns]
    missing = [column for column in wanted if column not in present]

    problems, unmatched = [], 0
    if decisions is not None and check_columns:                                        # RF-48
        named = dict.fromkeys(to_text(row[0]).strip() for row in [*decisions.table, *decisions.catalog])
        for column in named:
            if column not in present:
                problems.append(f"«{column}»: la columna no está en el archivo; sus decisiones no se aplicaron.")

    suggestions = separation_suggestions or {}
    entries, catalogs, summary, rows_for_totals = [], {}, {}, {}
    for column in wanted:
        if column not in present:
            continue
        if before_column is not None:
            before_column(column)
        name = present[column]
        current = list(df[name])
        original_name = f"{column}_ORIGINAL"
        # En NOMBRES_APELLIDOS el original es el de cada persona ya separada: la
        # columna _ORIGINAL repite la celda completa en todas (plan, T12).
        use_original = original_name in df.columns and column != _NAMES
        originals = list(df[original_name]) if use_original else current
        included = _included_rows(column, marks, separation)
        automatic, to_confirm = _automatic_outcomes(column, current, included, ids)

        outcomes, cache = [], {}
        for value, original, keep, status, row_id in zip(current, originals, included, separation, row_ids):
            if not keep:
                final = render(value, column)
                if column == _NAMES and status == _NOT_SEPARATED:                        # RF-25, RF-26
                    outcomes.append(Outcome(final, REVIEW, SEVERAL_NAMES, suggestions.get(row_id, "")))
                else:
                    outcomes.append(_unchanged_or_format(value, final))                  # RF-28
                continue
            key = (_value_key(original), _value_key(value))
            if key not in cache:
                cache[key] = apply_reviewed_table(original, automatic[_value_key(value)], column, table,
                                                  current=value)
            outcomes.append(cache[key])

        awaiting = set() if table is not None and column in table.columns else set(to_confirm)
        decided_by = None
        if decisions is not None:
            outcomes, decided_by, awaiting, missed = apply_overrides(
                column, originals, current, outcomes, decisions, awaiting, problems)
            unmatched += missed
        df[name] = [outcome.final for outcome in outcomes]
        entries.extend(_table_entries(column, originals, outcomes, row_ids, awaiting, decided_by))
        for i, outcome in enumerate(outcomes):
            if outcome.pending:
                pending[i].append(column)
                marks[i].append(MARK_PENDING)
            if outcome.not_a_person:
                marks[i].append(MARK_NOT_A_PERSON)
        catalogs[column] = _catalog(outcomes, included)
        summary[column] = _summary(originals, outcomes, awaiting)
        rows_for_totals[column] = list(zip(originals, outcomes))

    totals = verify_totals(rows_for_totals, n)                                           # RF-92
    df["_marks"] = [tuple(dict.fromkeys(row)) for row in marks]
    df["_pending"] = [tuple(dict.fromkeys(row)) for row in pending]
    return StandardizationResult(df, entries, catalogs, summary, totals, missing, unmatched, problems, decisions)


def add_observation_column(df):
    """RF-78: "Observación estandarización" al final, con las marcas de cada fila separadas por "; "."""
    out = df.drop(columns=[OBSERVATION]) if OBSERVATION in df.columns else df.copy()
    marks = out["_marks"] if "_marks" in out.columns else [()] * len(out)
    out[OBSERVATION] = ["; ".join(row) for row in marks]
    return out
