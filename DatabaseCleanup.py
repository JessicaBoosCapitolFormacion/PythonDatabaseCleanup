import os
import difflib
import re
import unicodedata

import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

INPUT_FOLDER = r"input"
OUTPUT_FOLDER = r"output"
LOG_FOLDER = r"logs"


# ------------------------------------------------------------
# EXISTING CSV COLUMN NAMES
# ------------------------------------------------------------

PROVINCE_COLUMN = "Provincia"
COUNTRY_COLUMN = "País"
CITY_COLUMN = "Ciudad"


# ------------------------------------------------------------
# ID COLUMN
# ------------------------------------------------------------

ID_COLUMN = None

ID_CANDIDATES = [
    "ID",
    "Id",
    "id",
    "ID de registro",
    "ID Cliente",
    "Id Cliente",
    "ID cliente",
    "Id cliente",
    "Cliente ID",
    "Cliente Id",
    "ClienteID",
    "ClienteId",
    "Identificador",
    "Identificación",
    "Identificacion",
]


# ------------------------------------------------------------
# EMAIL COLUMN
# ------------------------------------------------------------

EMAIL_COLUMN = None

EMAIL_CANDIDATES = [
    "email",
    "Email",
    "EMAIL",
    "e-mail",
    "E-mail",
    "Correo",
    "correo",
    "Correo electrónico",
    "Correo electronico",
    "Email Address",
    "Email address",
]


# ------------------------------------------------------------
# OPTIONAL EXPLICIT COLUMN NAMES
# ------------------------------------------------------------

POSTAL_CODE_COLUMN = None
ADDRESS_COLUMN = None


# ------------------------------------------------------------
# CONFIG FILES
# ------------------------------------------------------------

PROVINCES_FILE = r"config/provinces.txt"
PROVINCE_RULES_FILE = r"config/provinces_rules.csv"

COUNTRIES_FILE = r"config/countries.txt"
COUNTRY_RULES_FILE = r"config/countries_rules.csv"

SPANISH_POSTAL_PREFIXES_FILE = (
    r"config/spanish_postal_prefixes.csv"
)


# ------------------------------------------------------------
# FUZZY MATCHING
# ------------------------------------------------------------

FUZZY_CUTOFF = 0.90


# ============================================================
# COLUMN AUTO-DETECTION
# ============================================================

POSTAL_CODE_CANDIDATES = [
    "Código Postal",
    "Codigo Postal",
    "Código postal",
    "Codigo postal",
    "CP",
    "C.P.",
    "Postal Code",
    "Postal code",
    "PostalCode",
    "ZIP",
    "Zip",
    "ZIP Code",
    "Zip Code",
]


ADDRESS_CANDIDATES = [
    "Dirección",
    "Direccion",
    "dirección",
    "direccion",
    "Address",
    "address",
    "Domicilio",
    "domicilio",
]


# ============================================================
# GENERAL HELPERS
# ============================================================

def safe_string(value):
    """Convert a dataframe value to a clean string."""

    if value is None or pd.isna(value):
        return ""

    return str(value).strip()


def normalize(text):
    """
    Normalize text for comparison.

    Examples:
        Málaga  -> malaga
        MALAGA  -> malaga
        España  -> espana
        València -> valencia
    """

    if text is None or pd.isna(text):
        return ""

    text = str(text).strip()

    if not text:
        return ""

    normalized = unicodedata.normalize(
        "NFKD",
        text,
    )

    normalized = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )

    return normalized.casefold()


# ============================================================
# LOAD OFFICIAL VALUES
# ============================================================

def load_values(path):
    """
    Load official values from a text file.

    Each non-empty line is treated as one permitted value.
    """

    values = []

    with open(
        path,
        "r",
        encoding="utf-8-sig",
    ) as file:

        for line in file:

            value = line.strip()

            if value:
                values.append(value)

    return values


# ============================================================
# ENCODING REPAIR
# ============================================================

def repair_mojibake(text):
    """
    Repair common UTF-8/Windows-1252 mojibake.

    Examples:
        MÃ¡laga -> Málaga
        EspaÃ±a -> España
    """

    if text is None or pd.isna(text):
        return ""

    text = str(text)

    if (
        "Ã" in text
        or "Â" in text
        or "â" in text
    ):

        try:

            repaired = (
                text
                .encode("latin1")
                .decode("utf-8")
            )

            return repaired

        except (
            UnicodeEncodeError,
            UnicodeDecodeError,
        ):

            pass

    return text


def contains_encoding_artifact(text):
    """Detect common encoding artifacts."""

    if text is None:
        return False

    text = str(text)

    suspicious_fragments = [
        "Ã",
        "Â",
        "â€",
        "â€™",
        "â€“",
        "â€”",
        "â€œ",
        "â€�",
        "�",
        "M�",
        "Espa�",
        "Pa�",
    ]

    return any(
        fragment in text
        for fragment in suspicious_fragments
    )


# ============================================================
# REPAIR USING OFFICIAL VALUES
# ============================================================

def repair_using_official_values(
    value,
    official_values,
):
    """
    Recover values containing the Unicode replacement
    character when there is exactly one structural match
    in the official list.
    """

    if value is None:
        return None

    value = str(value)

    if "�" not in value:
        return value

    candidates = []

    for official in official_values:

        official_string = str(official)

        if len(official_string) != len(value):
            continue

        possible = True

        for current, expected in zip(
            value,
            official_string,
        ):

            if current == "�":
                continue

            if current.casefold() != expected.casefold():
                possible = False
                break

        if possible:
            candidates.append(official_string)

    if len(candidates) == 1:
        return candidates[0]

    return value


# ============================================================
# LOAD RULES
# ============================================================

def load_rules(path):
    """
    Load correction rules from CSV.

    Expected columns:

        wrong,correct
    """

    df = None
    last_error = None

    encodings = [
        "utf-8-sig",
        "utf-8",
        "cp1252",
        "latin1",
    ]

    for encoding in encodings:

        try:

            df = pd.read_csv(
                path,
                dtype=str,
                keep_default_na=False,
                encoding=encoding,
            )

            break

        except (
            UnicodeDecodeError,
            pd.errors.ParserError,
        ) as error:

            last_error = error

    if df is None:

        raise RuntimeError(
            f"Could not read rules file '{path}'. "
            f"Last error: {last_error}"
        )

    required_columns = {
        "wrong",
        "correct",
    }

    missing_columns = (
        required_columns
        - set(df.columns)
    )

    if missing_columns:

        raise ValueError(
            f"Rules file '{path}' is missing required "
            f"columns: {', '.join(sorted(missing_columns))}"
        )

    rules = {}

    for row_number, row in df.iterrows():

        wrong = str(
            row["wrong"]
        ).strip()

        correct = str(
            row["correct"]
        ).strip()

        if not wrong:
            continue

        if not correct:

            raise ValueError(
                f"Empty correction target at row "
                f"{row_number + 2} in {path}"
            )

        repaired_wrong = repair_mojibake(wrong)
        repaired_correct = repair_mojibake(correct)

        rules[repaired_wrong] = repaired_correct

        if repaired_wrong != wrong:
            rules[wrong] = repaired_correct

    return rules


# ============================================================
# LOAD POSTAL PREFIXES
# ============================================================

def load_postal_prefixes(path):
    """
    Load Spanish postal-code prefixes.

    Expected columns:

        prefix,province
    """

    df = pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )

    required_columns = {
        "prefix",
        "province",
    }

    missing_columns = (
        required_columns
        - set(df.columns)
    )

    if missing_columns:

        raise ValueError(
            f"Postal prefix file '{path}' is missing "
            f"required columns: "
            f"{', '.join(sorted(missing_columns))}"
        )

    prefixes = {}

    for row_number, row in df.iterrows():

        prefix = str(
            row["prefix"]
        ).strip()

        province = repair_mojibake(
            str(row["province"]).strip()
        )

        if not prefix:
            continue

        if not province:

            raise ValueError(
                f"Province is empty at row "
                f"{row_number + 2} in {path}"
            )

        if not re.fullmatch(r"\d{2}", prefix):

            raise ValueError(
                f"Postal prefix '{prefix}' at row "
                f"{row_number + 2} in {path} is invalid. "
                "It must contain exactly two digits."
            )

        if prefix in prefixes:

            raise ValueError(
                f"Postal prefix '{prefix}' is duplicated "
                f"in {path}"
            )

        prefixes[prefix] = province

    return prefixes


# ============================================================
# CONFIGURATION VALIDATION
# ============================================================

def validate_configuration(
    values,
    rules,
    config_name,
    field_name,
):
    """Validate official values and correction rules."""

    if not values:

        raise ValueError(
            f"No values were found in {config_name}"
        )

    normalized_seen = {}

    for value in values:

        normalized = normalize(value)

        if normalized in normalized_seen:

            other = normalized_seen[normalized]

            raise ValueError(
                f"Duplicate normalized values in "
                f"{config_name}: '{other}' and '{value}'"
            )

        normalized_seen[normalized] = value

    official_normalized = {
        normalize(value): value
        for value in values
    }

    for wrong, correct in rules.items():

        repaired_correct = repair_using_official_values(
            correct,
            values,
        )

        normalized_correct = normalize(
            repaired_correct
        )

        if normalized_correct not in official_normalized:

            raise ValueError(
                f"Rule '{wrong}' -> '{correct}' in "
                f"{config_name} points to a value that "
                f"does not exist in the official "
                f"{field_name} list."
            )


def validate_postal_prefix_configuration(
    postal_prefixes,
    official_provinces,
):
    """Ensure postal prefix provinces are official."""

    official_normalized = {
        normalize(value): value
        for value in official_provinces
    }

    for prefix, province in postal_prefixes.items():

        normalized_province = normalize(province)

        if normalized_province not in official_normalized:

            raise ValueError(
                f"Postal prefix '{prefix}' points to "
                f"province '{province}', but that province "
                "does not exist in provinces.txt."
            )


# ============================================================
# BUILD LOOKUP TABLES
# ============================================================

def build_lookup_tables(
    official_values,
    rules,
):
    """Build normalized lookup dictionaries."""

    normalized_official = {
        normalize(value): value
        for value in official_values
    }

    normalized_rules = {}

    for wrong, correct in rules.items():

        repaired_wrong = repair_using_official_values(
            wrong,
            official_values,
        )

        repaired_correct = repair_using_official_values(
            correct,
            official_values,
        )

        normalized_wrong = normalize(repaired_wrong)
        normalized_correct = normalize(repaired_correct)

        if normalized_correct in normalized_official:

            normalized_rules[
                normalized_wrong
            ] = normalized_official[
                normalized_correct
            ]

    return (
        normalized_official,
        normalized_rules,
    )


# ============================================================
# FUZZY MATCH
# ============================================================

def fuzzy_match(
    normalized_value,
    normalized_official,
):
    """Find a conservative fuzzy match."""

    if not normalized_value:
        return None, None

    candidates = []

    for (
        official_normalized,
        official_value,
    ) in normalized_official.items():

        score = difflib.SequenceMatcher(
            None,
            normalized_value,
            official_normalized,
        ).ratio()

        candidates.append(
            (
                score,
                official_value,
            )
        )

    if not candidates:
        return None, None

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    best_score = candidates[0][0]
    best_value = candidates[0][1]

    if best_score < FUZZY_CUTOFF:
        return None, None

    if len(candidates) > 1:

        second_score = candidates[1][0]

        if best_score - second_score < 0.03:
            return None, None

    return best_value, best_score


# ============================================================
# PROVINCE / COUNTRY CLEANING
# ============================================================

def clean_value(
    value,
    official_values,
    exact_rules,
    normalized_official,
    normalized_rules,
):
    """
    Clean one province or country value.

    Returns:
        cleaned value
        method
        fuzzy score
        reason
    """

    if value is None or pd.isna(value):

        return (
            "",
            "empty",
            None,
            "The value was empty.",
        )

    original = str(value).strip()

    if not original:

        return (
            "",
            "empty",
            None,
            "The value was empty.",
        )

    # --------------------------------------------------------
    # Exact official value.
    # --------------------------------------------------------

    if original in official_values:

        return (
            original,
            "exact",
            None,
            "No changes were made.",
        )

    # --------------------------------------------------------
    # Exact configured rule.
    # --------------------------------------------------------

    if original in exact_rules:

        corrected = repair_using_official_values(
            exact_rules[original],
            official_values,
        )

        return (
            corrected,
            "alias",
            None,
            (
                f"Applied a configured correction rule: "
                f"'{original}' -> '{corrected}'."
            ),
        )

    # --------------------------------------------------------
    # Standard mojibake repair.
    # --------------------------------------------------------

    repaired = repair_mojibake(original)

    # --------------------------------------------------------
    # Replacement-character repair.
    # --------------------------------------------------------

    repaired = repair_using_official_values(
        repaired,
        official_values,
    )

    if repaired != original:

        if repaired in official_values:

            return (
                repaired,
                "encoding",
                None,
                (
                    f"Fixed character encoding: "
                    f"'{original}' -> '{repaired}'."
                ),
            )

        if repaired in exact_rules:

            corrected = repair_using_official_values(
                exact_rules[repaired],
                official_values,
            )

            return (
                corrected,
                "alias",
                None,
                (
                    f"Fixed character encoding and applied "
                    f"a configured correction: "
                    f"'{original}' -> '{corrected}'."
                ),
            )

    normalized_value = normalize(repaired)

    if not normalized_value:

        return (
            "",
            "empty",
            None,
            "The value was empty.",
        )

    # --------------------------------------------------------
    # Normalized alias.
    # --------------------------------------------------------

    if normalized_value in normalized_rules:

        corrected = normalized_rules[
            normalized_value
        ]

        return (
            corrected,
            "alias",
            None,
            (
                "Applied a configured correction after "
                "ignoring capitalization and accents: "
                f"'{original}' -> '{corrected}'."
            ),
        )

    # --------------------------------------------------------
    # Normalized official value.
    # --------------------------------------------------------

    if normalized_value in normalized_official:

        corrected = normalized_official[
            normalized_value
        ]

        if corrected != original:

            return (
                corrected,
                "normalized",
                None,
                (
                    "Normalized capitalization, accents, "
                    f"or spelling: '{original}' -> "
                    f"'{corrected}'."
                ),
            )

        return (
            corrected,
            "exact",
            None,
            "No changes were made.",
        )

    # --------------------------------------------------------
    # Conservative fuzzy match.
    # --------------------------------------------------------

    corrected, score = fuzzy_match(
        normalized_value,
        normalized_official,
    )

    if corrected is not None:

        return (
            corrected,
            "fuzzy",
            score,
            (
                "Applied a conservative fuzzy match to "
                "the official list: "
                f"'{original}' -> '{corrected}'."
            ),
        )

    return (
        original,
        "unmatched",
        None,
        (
            "No safe match was found; the original value "
            "was kept."
        ),
    )


# ============================================================
# PROCESS PROVINCE / COUNTRY COLUMN
# ============================================================

def process_column(
    df,
    column_name,
    official_values,
    rules,
    normalized_official,
    normalized_rules,
):
    """Clean a province or country column."""

    if column_name not in df.columns:

        raise ValueError(
            f"Column '{column_name}' was not found. "
            f"Available columns: {list(df.columns)}"
        )

    cleaned_values = []

    for value in df[column_name]:

        corrected, _, _, _ = clean_value(
            value=value,
            official_values=official_values,
            exact_rules=rules,
            normalized_official=normalized_official,
            normalized_rules=normalized_rules,
        )

        cleaned_values.append(corrected)

    df[column_name] = cleaned_values

    return df


# ============================================================
# CITY FORMATTING
# ============================================================

def format_city_capitalization(value):
    """Apply conservative capitalization to a city."""

    if value is None or pd.isna(value):
        return ""

    value = str(value).strip()

    if not value:
        return ""

    value = " ".join(value.split())

    words = value.casefold().split(" ")

    small_words = {
        "de",
        "del",
        "la",
        "las",
        "los",
        "el",
        "y",
        "e",
        "da",
        "do",
        "das",
        "dos",
    }

    formatted_words = []

    for index, word in enumerate(words):

        if not word:
            continue

        if "'" in word:

            parts = word.split("'")

            formatted_parts = []

            for part in parts:

                if not part:
                    formatted_parts.append("")
                else:
                    formatted_parts.append(
                        part.capitalize()
                    )

            formatted_word = "'".join(
                formatted_parts
            )

        elif (
            index > 0
            and word in small_words
        ):

            formatted_word = word.lower()

        else:

            formatted_word = word.capitalize()

        formatted_words.append(formatted_word)

    return " ".join(formatted_words)


def looks_like_non_city(
    value,
    normalized_countries,
):
    """
    Identify values that look suspicious for a city field.
    """

    if value is None or pd.isna(value):
        return None

    value = str(value).strip()

    if not value:
        return None

    lowered = value.casefold()

    placeholders = {
        "-",
        "--",
        "---",
        ".",
        "...",
        "?",
        "??",
        "???",
        "n/a",
        "na",
        "n.a.",
        "n.a",
        "null",
        "none",
        "unknown",
        "desconocido",
        "sin datos",
        "sin dato",
        "no consta",
        "no disponible",
    }

    if lowered in placeholders:
        return "placeholder"

    if contains_encoding_artifact(value):
        return "encoding_artifact"

    if "," in value or ";" in value:
        return "multiple_values"

    address_patterns = [
        r"\bcalle\b",
        r"\bc\/\b",
        r"\bc\.\b",
        r"\bcarrer\b",
        r"\bcarretera\b",
        r"\bcamino\b",
        r"\bavenida\b",
        r"\bav\.\b",
        r"\bavda\b",
        r"\bavda\.\b",
        r"\bpaseo\b",
        r"\bplaza\b",
        r"\bportal\b",
        r"\bpuerta\b",
        r"\bpolígono\b",
        r"\bpoligono\b",
        r"\bstreet\b",
        r"\broad\b",
        r"\bavenue\b",
        r"\bave\.\b",
        r"\bdrive\b",
        r"\bdr\.\b",
        r"\blane\b",
        r"\bln\.\b",
        r"\brd\.\b",
    ]

    for pattern in address_patterns:

        if re.search(pattern, lowered):
            return "possible_address"

    if (
        re.search(r"[A-Za-zÀ-ÿ]", value)
        and re.search(r"\d", value)
    ):
        return "contains_number"

    if re.fullmatch(r"\d{5}", value):
        return "possible_postal_code"

    if re.fullmatch(r"\d+", value):
        return "numeric_value"

    normalized_value = normalize(value)

    if normalized_value in normalized_countries:
        return "country_value"

    comment_patterns = [
        r"\bllamar\b",
        r"\bllame\b",
        r"\bcontactar\b",
        r"\bcontacte\b",
        r"\bcliente\b",
        r"\bcomentario\b",
        r"\bcomentarios\b",
        r"\bobservaciones\b",
        r"\bobservación\b",
        r"\bobservacion\b",
        r"\bnota\b",
        r"\bnotas\b",
        r"\bemail\b",
        r"\be-mail\b",
        r"\bcorreo\b",
        r"\bteléfono\b",
        r"\btelefono\b",
        r"\bphone\b",
        r"\bcall\b",
    ]

    for pattern in comment_patterns:

        if re.search(pattern, lowered):
            return "possible_comment"

    return None


def process_city_column(
    df,
    column_name,
    normalized_countries,
):
    """Clean city formatting and return review information."""

    if column_name not in df.columns:

        raise ValueError(
            f"Column '{column_name}' was not found. "
            f"Available columns: {list(df.columns)}"
        )

    cleaned_values = []
    review_rows = []

    for row_number, value in enumerate(
        df[column_name],
        start=2,
    ):

        original = safe_string(value)

        repaired = repair_mojibake(original)

        cleaned = " ".join(
            repaired.split()
        )

        formatted = format_city_capitalization(
            cleaned
        )

        cleaned_values.append(formatted)

        review_reason = looks_like_non_city(
            formatted,
            normalized_countries,
        )

        if review_reason:

            review_rows.append(
                {
                    "Row": row_number,
                    "Field": column_name,
                    "Value": formatted,
                    "Reason": review_reason,
                    "Details": (
                        "The city value looks unusual and "
                        "should be checked manually."
                    ),
                }
            )

    df[column_name] = cleaned_values

    return df, review_rows


# ============================================================
# ADDRESS FORMATTING
# ============================================================

def format_address_capitalization(value):
    """Apply conservative capitalization to an address."""

    if value is None or pd.isna(value):
        return ""

    value = str(value).strip()

    if not value:
        return ""

    value = " ".join(value.split())
    value = value.casefold()

    small_words = {
        "de",
        "del",
        "la",
        "las",
        "los",
        "el",
        "y",
        "e",
        "da",
        "do",
        "das",
        "dos",
    }

    words = value.split(" ")

    formatted_words = []

    for index, word in enumerate(words):

        if not word:
            continue

        if "'" in word:

            parts = word.split("'")

            formatted_parts = []

            for part in parts:

                if not part:
                    formatted_parts.append("")
                else:
                    formatted_parts.append(
                        part.capitalize()
                    )

            formatted_word = "'".join(
                formatted_parts
            )

        else:

            formatted_word = word.capitalize()

        if (
            index > 0
            and word in small_words
        ):

            formatted_word = word.lower()

        formatted_words.append(formatted_word)

    return " ".join(formatted_words)


def process_address_column(
    df,
    address_column,
):
    """Clean address formatting and return review information."""

    if address_column not in df.columns:

        raise ValueError(
            f"Address column '{address_column}' was not found."
        )

    cleaned_values = []
    review_rows = []

    for row_number, value in enumerate(
        df[address_column],
        start=2,
    ):

        original = safe_string(value)

        repaired = repair_mojibake(
            original
        )

        cleaned = " ".join(
            repaired.split()
        )

        formatted = format_address_capitalization(
            cleaned
        )

        cleaned_values.append(formatted)

        if (
            formatted
            and contains_encoding_artifact(formatted)
        ):

            review_rows.append(
                {
                    "Row": row_number,
                    "Field": address_column,
                    "Value": formatted,
                    "Reason": "encoding_error",
                    "Details": (
                        "A possible encoding problem remains "
                        "after automatic repair."
                    ),
                }
            )

    df[address_column] = cleaned_values

    return df, review_rows


# ============================================================
# POSTAL CODE PROCESSING
# ============================================================

def clean_postal_code_format(value):
    """Clean postal code formatting without guessing."""

    if value is None or pd.isna(value):
        return ""

    original = str(value).strip()

    if not original:
        return ""

    return re.sub(r"\s+", "", original)


def process_postal_code_column(
    df,
    postal_column,
    province_column,
    normalized_provinces,
    postal_prefixes,
):
    """
    Clean postal codes and return review information.
    """

    if postal_column not in df.columns:

        raise ValueError(
            f"Postal code column '{postal_column}' was not found."
        )

    if province_column not in df.columns:

        raise ValueError(
            f"Province column '{province_column}' was not found."
        )

    cleaned_values = []
    review_rows = []

    for row_number, (
        postal_value,
        province_value,
    ) in enumerate(
        zip(
            df[postal_column],
            df[province_column],
        ),
        start=2,
    ):

        cleaned = clean_postal_code_format(
            postal_value
        )

        cleaned_values.append(cleaned)

        if not cleaned:
            continue

        province = safe_string(province_value)

        if re.fullmatch(
            r"\d{5}",
            cleaned,
        ):

            prefix = cleaned[:2]

            expected_province = postal_prefixes.get(
                prefix
            )

            if expected_province is None:

                review_rows.append(
                    {
                        "Row": row_number,
                        "Field": postal_column,
                        "Value": cleaned,
                        "Reason": "unknown_postal_prefix",
                        "Details": (
                            f"Postal prefix '{prefix}' does not "
                            "exist in the configured Spanish "
                            "postal prefix list."
                        ),
                    }
                )

                continue

            if not province:

                review_rows.append(
                    {
                        "Row": row_number,
                        "Field": postal_column,
                        "Value": cleaned,
                        "Reason": "empty_province",
                        "Details": (
                            f"The postal code indicates "
                            f"'{expected_province}', but the "
                            "province field is empty."
                        ),
                    }
                )

                continue

            normalized_province = normalize(
                province
            )

            if normalized_province not in normalized_provinces:

                review_rows.append(
                    {
                        "Row": row_number,
                        "Field": postal_column,
                        "Value": cleaned,
                        "Reason": "unrecognized_province",
                        "Details": (
                            "The postal code format is valid, "
                            "but the province is not recognized "
                            "in the official province list."
                        ),
                    }
                )

                continue

            official_province = normalized_provinces[
                normalized_province
            ]

            if normalize(expected_province) != normalize(
                official_province
            ):

                review_rows.append(
                    {
                        "Row": row_number,
                        "Field": postal_column,
                        "Value": cleaned,
                        "Reason": "postal_province_mismatch",
                        "Details": (
                            f"Postal prefix {prefix} corresponds "
                            f"to '{expected_province}', but the "
                            f"province is '{official_province}'. "
                            "Neither value was changed automatically."
                        ),
                    }
                )

            continue

        if re.search(
            r"[A-Za-zÀ-ÿ]",
            cleaned,
        ):

            review_rows.append(
                {
                    "Row": row_number,
                    "Field": postal_column,
                    "Value": cleaned,
                    "Reason": "contains_letters",
                    "Details": (
                        "The postal code contains letters. "
                        "Spanish postal codes must contain "
                        "five digits."
                    ),
                }
            )

            continue

        if re.search(
            r"[^\d]",
            cleaned,
        ):

            review_rows.append(
                {
                    "Row": row_number,
                    "Field": postal_column,
                    "Value": cleaned,
                    "Reason": "invalid_characters",
                    "Details": (
                        "The postal code contains characters "
                        "other than digits."
                    ),
                }
            )

            continue

        if cleaned.isdigit():

            review_rows.append(
                {
                    "Row": row_number,
                    "Field": postal_column,
                    "Value": cleaned,
                    "Reason": "invalid_length",
                    "Details": (
                        "The postal code contains only digits "
                        "but does not contain exactly five digits."
                    ),
                }
            )

    df[postal_column] = cleaned_values

    return df, review_rows


# ============================================================
# CSV LOADING
# ============================================================

def load_csv(path):
    """Try several common CSV encodings."""

    encodings = [
        "utf-8-sig",
        "utf-8",
        "cp1252",
        "latin1",
    ]

    last_error = None

    for encoding in encodings:

        try:

            print(
                f"Trying CSV encoding: {encoding}"
            )

            df = pd.read_csv(
                path,
                dtype=str,
                keep_default_na=False,
                encoding=encoding,
            )

            print(
                f"Loaded successfully using {encoding}"
            )

            return df

        except (
            UnicodeDecodeError,
            pd.errors.ParserError,
        ) as error:

            last_error = error

    raise RuntimeError(
        "Could not read the CSV with the available "
        f"encodings. Last error: {last_error}"
    )


# ============================================================
# FIND INPUT FILES
# ============================================================

def get_input_files(folder):

    if not os.path.isdir(folder):

        raise FileNotFoundError(
            f"Input folder does not exist: {folder}"
        )

    files = [
        os.path.join(
            folder,
            filename,
        )
        for filename in os.listdir(folder)
        if filename.lower().endswith(".csv")
    ]

    files.sort()

    if not files:

        raise FileNotFoundError(
            f"No CSV files were found in: {folder}"
        )

    return files


# ============================================================
# FIND COLUMN
# ============================================================

def find_column(
    df,
    explicit_column,
    candidates,
    field_description,
):
    """Find a column using explicit name or common candidates."""

    if explicit_column:

        if explicit_column not in df.columns:

            raise ValueError(
                f"Configured {field_description} column "
                f"'{explicit_column}' does not exist. "
                f"Available columns: {list(df.columns)}"
            )

        return explicit_column

    for candidate in candidates:

        if candidate in df.columns:
            return candidate

    normalized_columns = {
        normalize(column): column
        for column in df.columns
    }

    for candidate in candidates:

        normalized_candidate = normalize(candidate)

        if normalized_candidate in normalized_columns:

            return normalized_columns[
                normalized_candidate
            ]

    raise ValueError(
        f"Could not automatically find the "
        f"{field_description} column. "
        f"Available columns: {list(df.columns)}"
    )


def find_id_column(df):

    return find_column(
        df=df,
        explicit_column=ID_COLUMN,
        candidates=ID_CANDIDATES,
        field_description="ID",
    )


def find_email_column(df):

    return find_column(
        df=df,
        explicit_column=EMAIL_COLUMN,
        candidates=EMAIL_CANDIDATES,
        field_description="email",
    )


# ============================================================
# OUTPUT PATHS
# ============================================================

def build_output_paths(input_file):

    filename = os.path.basename(input_file)

    base_name = os.path.splitext(filename)[0]

    return {
        "cleaned": os.path.join(
            OUTPUT_FOLDER,
            f"{base_name}_cleaned.csv",
        ),

        "changes": os.path.join(
            OUTPUT_FOLDER,
            f"{base_name}_changes.csv",
        ),

        "review": os.path.join(
            OUTPUT_FOLDER,
            f"{base_name}_review.csv",
        ),
    }


# ============================================================
# CHANGE DETAILS
# ============================================================

def explain_field_change(
    field_name,
    original,
    cleaned,
):
    """Explain one field change in English."""

    original = safe_string(original)
    cleaned = safe_string(cleaned)

    if original == cleaned:
        return "No changes were made."

    if not original and cleaned:

        return (
            f"The field was empty and now contains "
            f"'{cleaned}'."
        )

    if original and not cleaned:

        return (
            "The original value became empty during "
            "automatic cleaning."
        )

    repaired = repair_mojibake(original)

    if repaired != original:

        return (
            f"Character encoding was repaired: "
            f"'{original}' -> '{cleaned}'."
        )

    if field_name == CITY_COLUMN:

        if normalize(original) == normalize(cleaned):

            return (
                "City capitalization, spacing, or accents "
                "were normalized."
            )

        return (
            f"City formatting was corrected: "
            f"'{original}' -> '{cleaned}'."
        )

    if field_name == ADDRESS_COLUMN:

        if normalize(original) == normalize(cleaned):

            return (
                "Address capitalization, spacing, or accents "
                "were normalized."
            )

        return (
            f"Address formatting was corrected: "
            f"'{original}' -> '{cleaned}'."
        )

    if field_name == PROVINCE_COLUMN:

        if normalize(original) == normalize(cleaned):

            return (
                "Province capitalization or accents "
                "were normalized."
            )

        return (
            f"Province was corrected using the official "
            f"configuration: '{original}' -> '{cleaned}'."
        )

    if field_name == COUNTRY_COLUMN:

        if normalize(original) == normalize(cleaned):

            return (
                "Country capitalization or accents "
                "were normalized."
            )

        return (
            f"Country was corrected using the official "
            f"configuration: '{original}' -> '{cleaned}'."
        )

    if field_name == POSTAL_CODE_COLUMN:

        return (
            f"Postal code formatting was normalized: "
            f"'{original}' -> '{cleaned}'."
        )

    return (
        f"The field was changed from "
        f"'{original}' to '{cleaned}'."
    )


# ============================================================
# BUILD CHANGE REPORT
# ============================================================

def create_change_report(
    original_df,
    cleaned_df,
    id_column,
    email_column,
    address_column,
    city_column,
    province_column,
    country_column,
    postal_column,
):
    """
    Create one row per input record.

    The report contains exactly the requested comparison fields.
    """

    rows = []

    for index in range(len(original_df)):

        original_id = safe_string(
            original_df.iloc[index][id_column]
        )

        email = safe_string(
            cleaned_df.iloc[index][email_column]
        )

        old_address = safe_string(
            original_df.iloc[index][address_column]
        )

        new_address = safe_string(
            cleaned_df.iloc[index][address_column]
        )

        old_city = safe_string(
            original_df.iloc[index][city_column]
        )

        new_city = safe_string(
            cleaned_df.iloc[index][city_column]
        )

        old_province = safe_string(
            original_df.iloc[index][province_column]
        )

        new_province = safe_string(
            cleaned_df.iloc[index][province_column]
        )

        old_country = safe_string(
            original_df.iloc[index][country_column]
        )

        new_country = safe_string(
            cleaned_df.iloc[index][country_column]
        )

        old_postal = safe_string(
            original_df.iloc[index][postal_column]
        )

        new_postal = safe_string(
            cleaned_df.iloc[index][postal_column]
        )

        details = []

        field_pairs = [
            (
                "address",
                old_address,
                new_address,
            ),
            (
                "city",
                old_city,
                new_city,
            ),
            (
                "province",
                old_province,
                new_province,
            ),
            (
                "country",
                old_country,
                new_country,
            ),
            (
                "postal code",
                old_postal,
                new_postal,
            ),
        ]

        for label, old_value, new_value in field_pairs:

            if old_value != new_value:

                if label == "address":
                    details.append(
                        f"Address: {explain_field_change(address_column, old_value, new_value)}"
                    )

                elif label == "city":
                    details.append(
                        f"City: {explain_field_change(city_column, old_value, new_value)}"
                    )

                elif label == "province":
                    details.append(
                        f"Province: {explain_field_change(province_column, old_value, new_value)}"
                    )

                elif label == "country":
                    details.append(
                        f"Country: {explain_field_change(country_column, old_value, new_value)}"
                    )

                elif label == "postal code":
                    details.append(
                        f"Postal code: {explain_field_change(postal_column, old_value, new_value)}"
                    )

        if not details:

            change_details = "No changes were made."

        else:

            change_details = " ".join(details)

        rows.append(
            {
                "ID de registro": original_id,
                "email": email,
                "new address": new_address,
                "old address": old_address,
                "new city": new_city,
                "old city": old_city,
                "new province": new_province,
                "old province": old_province,
                "new country": new_country,
                "old country": old_country,
                "new postal code": new_postal,
                "old postal code": old_postal,
                "change details": change_details,
            }
        )

    columns = [
        "ID de registro",
        "email",
        "new address",
        "old address",
        "new city",
        "old city",
        "new province",
        "old province",
        "new country",
        "old country",
        "new postal code",
        "old postal code",
        "change details",
    ]

    return pd.DataFrame(
        rows,
        columns=columns,
    )


# ============================================================
# BUILD REVIEW REPORT
# ============================================================

def create_review_report(
    original_df,
    cleaned_df,
    id_column,
    review_rows,
):
    """
    Add record ID and original/new values to review items.
    """

    rows = []

    for item in review_rows:

        row_number = item["Row"]

        dataframe_index = row_number - 2

        record_id = safe_string(
            original_df.iloc[dataframe_index][id_column]
        )

        rows.append(
            {
                "ID de registro": record_id,
                "Row": row_number,
                "Field": item["Field"],
                "Value": item["Value"],
                "Reason": item["Reason"],
                "Details": item["Details"],
            }
        )

    columns = [
        "ID de registro",
        "Row",
        "Field",
        "Value",
        "Reason",
        "Details",
    ]

    return pd.DataFrame(
        rows,
        columns=columns,
    )


# ============================================================
# DOCUMENTATION
# ============================================================

def create_documentation():

    documentation_file = os.path.join(
        OUTPUT_FOLDER,
        "CLEANUP_DOCUMENTATION.md",
    )

    documentation = r"""# Database Cleanup Documentation

## Output files

For each input CSV, the script creates three output files.

### 1. Cleaned file

`<name>_cleaned.csv`

This is the complete original dataset after automatic cleaning.

All original columns are preserved.

### 2. Changes file

`<name>_changes.csv`

This contains one row per input record.

Columns:

- `ID de registro`
- `email`
- `new address`
- `old address`
- `new city`
- `old city`
- `new province`
- `old province`
- `new country`
- `old country`
- `new postal code`
- `old postal code`
- `change details`

The geographic values themselves are preserved in their original
language. For example, Spanish city, province, country, and address
values remain Spanish.

The explanations in `change details` are written in English.

Every input record is included, including records where no changes
were necessary.

### 3. Review file

`<name>_review.csv`

This contains only values that require manual review.

Examples include:

- postal/province mismatches
- unknown postal prefixes
- suspicious city values
- possible addresses stored in the city field
- possible encoding problems
- invalid postal code formats

## Cleaning rules

### Provinces

Province values are checked against:

`config/provinces.txt`

Configured corrections are read from:

`config/provinces_rules.csv`

The script can apply:

- explicit correction rules
- encoding repair
- capitalization/accent normalization
- conservative fuzzy matching

### Countries

Country values are checked against:

`config/countries.txt`

Configured corrections are read from:

`config/countries_rules.csv`

### Cities

Cities are treated as free text.

The script does not require cities to exist in a closed official list.

It applies conservative:

- encoding repair
- whitespace cleanup
- capitalization

Suspicious values are sent to the review file rather than being
automatically replaced.

### Addresses

Addresses are cleaned using:

- encoding repair
- whitespace cleanup
- capitalization

The script does not attempt to verify whether an address physically
exists.

### Postal codes

Spanish postal codes are expected to contain five digits.

The first two digits are checked against:

`config/spanish_postal_prefixes.csv`

If the postal code conflicts with the province, the values are not
automatically changed. The record is placed in the review file.

## Output language

The actual geographic data is not translated.

For example:

`València`

remains:

`València`

The script's explanations, report headers, review reasons, console
messages, and documentation are written in English, except for the
specific requested geographic column name:

`ID de registro`
"""

    with open(
        documentation_file,
        "w",
        encoding="utf-8",
    ) as file:

        file.write(documentation)

    return documentation_file


# ============================================================
# CREATE FOLDERS
# ============================================================

os.makedirs(
    OUTPUT_FOLDER,
    exist_ok=True,
)

os.makedirs(
    LOG_FOLDER,
    exist_ok=True,
)


# ============================================================
# LOAD CONFIGURATION
# ============================================================

print("===================================")
print("LOADING CONFIGURATION")
print("===================================")


print("\nLoading provinces...")

OFFICIAL_PROVINCES = load_values(
    PROVINCES_FILE
)

PROVINCE_RULES = load_rules(
    PROVINCE_RULES_FILE
)

validate_configuration(
    OFFICIAL_PROVINCES,
    PROVINCE_RULES,
    PROVINCES_FILE,
    "provinces",
)

(
    NORMALIZED_PROVINCES,
    NORMALIZED_PROVINCE_RULES,
) = build_lookup_tables(
    OFFICIAL_PROVINCES,
    PROVINCE_RULES,
)


print("Loading countries...")

OFFICIAL_COUNTRIES = load_values(
    COUNTRIES_FILE
)

COUNTRY_RULES = load_rules(
    COUNTRY_RULES_FILE
)

validate_configuration(
    OFFICIAL_COUNTRIES,
    COUNTRY_RULES,
    COUNTRIES_FILE,
    "countries",
)

(
    NORMALIZED_COUNTRIES,
    NORMALIZED_COUNTRY_RULES,
) = build_lookup_tables(
    OFFICIAL_COUNTRIES,
    COUNTRY_RULES,
)


print("Loading Spanish postal prefixes...")

SPANISH_POSTAL_PREFIXES = load_postal_prefixes(
    SPANISH_POSTAL_PREFIXES_FILE
)

validate_postal_prefix_configuration(
    SPANISH_POSTAL_PREFIXES,
    OFFICIAL_PROVINCES,
)


print(
    f"\nOfficial provinces loaded: "
    f"{len(OFFICIAL_PROVINCES)}"
)

print(
    f"Province rules loaded: "
    f"{len(PROVINCE_RULES)}"
)

print(
    f"Official countries loaded: "
    f"{len(OFFICIAL_COUNTRIES)}"
)

print(
    f"Country rules loaded: "
    f"{len(COUNTRY_RULES)}"
)

print(
    f"Spanish postal prefixes loaded: "
    f"{len(SPANISH_POSTAL_PREFIXES)}"
)


# ============================================================
# CREATE DOCUMENTATION
# ============================================================

documentation_file = create_documentation()

print(
    f"\nDocumentation created: "
    f"{documentation_file}"
)


# ============================================================
# FIND INPUT FILES
# ============================================================

print("\n===================================")
print("FINDING INPUT FILES")
print("===================================")

input_files = get_input_files(
    INPUT_FOLDER
)

print(
    f"Found {len(input_files)} CSV file(s):"
)

for input_file in input_files:

    print(
        f"  - {input_file}"
    )


# ============================================================
# PROCESS ALL INPUT FILES
# ============================================================

successful_files = []
failed_files = []


for file_number, input_file in enumerate(
    input_files,
    start=1,
):

    print("\n\n")
    print("===================================")
    print(
        f"PROCESSING FILE "
        f"{file_number}/{len(input_files)}"
    )
    print("===================================")

    print(
        f"Input file: {input_file}"
    )

    try:

        paths = build_output_paths(
            input_file
        )


        # ====================================================
        # LOAD INPUT
        # ====================================================

        original_df = load_csv(
            input_file
        )

        original_df = original_df.copy()

        df = original_df.copy()


        # ====================================================
        # DISPLAY COLUMNS
        # ====================================================

        print("\nDetected columns:")

        for column in df.columns:

            print(
                f"  - {column}"
            )


        # ====================================================
        # FIND REQUIRED COLUMNS
        # ====================================================

        id_column = find_id_column(df)

        email_column = find_email_column(df)

        postal_column = find_column(
            df=df,
            explicit_column=POSTAL_CODE_COLUMN,
            candidates=POSTAL_CODE_CANDIDATES,
            field_description="postal code",
        )

        address_column = find_column(
            df=df,
            explicit_column=ADDRESS_COLUMN,
            candidates=ADDRESS_CANDIDATES,
            field_description="address",
        )

        required_columns = [
            PROVINCE_COLUMN,
            COUNTRY_COLUMN,
            CITY_COLUMN,
            postal_column,
            address_column,
            email_column,
        ]

        missing_columns = [
            column
            for column in required_columns
            if column not in df.columns
        ]

        if missing_columns:

            raise ValueError(
                "Missing required columns: "
                + ", ".join(missing_columns)
            )

        print(
            f"\nID column: {id_column}"
        )

        print(
            f"Email column: {email_column}"
        )

        print(
            f"Address column: {address_column}"
        )

        print(
            f"City column: {CITY_COLUMN}"
        )

        print(
            f"Province column: {PROVINCE_COLUMN}"
        )

        print(
            f"Country column: {COUNTRY_COLUMN}"
        )

        print(
            f"Postal code column: {postal_column}"
        )


        # ====================================================
        # REVIEW ITEMS
        # ====================================================

        review_rows = []


        # ====================================================
        # PROCESS PROVINCES
        # ====================================================

        print("\nProcessing provinces...")

        df = process_column(
            df=df,
            column_name=PROVINCE_COLUMN,
            official_values=OFFICIAL_PROVINCES,
            rules=PROVINCE_RULES,
            normalized_official=NORMALIZED_PROVINCES,
            normalized_rules=NORMALIZED_PROVINCE_RULES,
        )


        # ====================================================
        # PROCESS COUNTRIES
        # ====================================================

        print("Processing countries...")

        df = process_column(
            df=df,
            column_name=COUNTRY_COLUMN,
            official_values=OFFICIAL_COUNTRIES,
            rules=COUNTRY_RULES,
            normalized_official=NORMALIZED_COUNTRIES,
            normalized_rules=NORMALIZED_COUNTRY_RULES,
        )


        # ====================================================
        # PROCESS CITIES
        # ====================================================

        print("Processing cities...")

        (
            df,
            city_reviews,
        ) = process_city_column(
            df=df,
            column_name=CITY_COLUMN,
            normalized_countries=NORMALIZED_COUNTRIES,
        )

        review_rows.extend(
            city_reviews
        )


        # ====================================================
        # PROCESS POSTAL CODES
        # ====================================================

        print("Processing postal codes...")

        (
            df,
            postal_reviews,
        ) = process_postal_code_column(
            df=df,
            postal_column=postal_column,
            province_column=PROVINCE_COLUMN,
            normalized_provinces=NORMALIZED_PROVINCES,
            postal_prefixes=SPANISH_POSTAL_PREFIXES,
        )

        review_rows.extend(
            postal_reviews
        )


        # ====================================================
        # PROCESS ADDRESSES
        # ====================================================

        print("Processing addresses...")

        (
            df,
            address_reviews,
        ) = process_address_column(
            df=df,
            address_column=address_column,
        )

        review_rows.extend(
            address_reviews
        )


        # ====================================================
        # CREATE CHANGE REPORT
        # ====================================================

        print("Creating change report...")

        change_df = create_change_report(
            original_df=original_df,
            cleaned_df=df,
            id_column=id_column,
            email_column=email_column,
            address_column=address_column,
            city_column=CITY_COLUMN,
            province_column=PROVINCE_COLUMN,
            country_column=COUNTRY_COLUMN,
            postal_column=postal_column,
        )


        # ====================================================
        # CREATE REVIEW REPORT
        # ====================================================

        print("Creating review report...")

        review_df = create_review_report(
            original_df=original_df,
            cleaned_df=df,
            id_column=id_column,
            review_rows=review_rows,
        )


        # ====================================================
        # SAVE CLEANED FILE
        # ====================================================

        print(
            f"Saving cleaned file: "
            f"{paths['cleaned']}"
        )

        df.to_csv(
            paths["cleaned"],
            index=False,
            encoding="utf-8-sig",
        )


        # ====================================================
        # SAVE CHANGE REPORT
        # ====================================================

        print(
            f"Saving change report: "
            f"{paths['changes']}"
        )

        change_df.to_csv(
            paths["changes"],
            index=False,
            encoding="utf-8-sig",
        )


        # ====================================================
        # SAVE REVIEW REPORT
        # ====================================================

        print(
            f"Saving review report: "
            f"{paths['review']}"
        )

        review_df.to_csv(
            paths["review"],
            index=False,
            encoding="utf-8-sig",
        )


        # ====================================================
        # SUMMARY
        # ====================================================

        changed_records = 0

        for _, row in change_df.iterrows():

            if row["change details"] != "No changes were made.":

                changed_records += 1

        print("\n-----------------------------------")
        print("FILE COMPLETED")
        print("-----------------------------------")

        print(
            f"Rows processed:       {len(df)}"
        )

        print(
            f"Records with changes: {changed_records}"
        )

        print(
            f"Review items:         {len(review_df)}"
        )

        print(
            f"Output files:         3"
        )

        successful_files.append(
            input_file
        )


    except Exception as error:

        print("\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("ERROR PROCESSING FILE")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

        print(
            f"File: {input_file}"
        )

        print(
            f"Error: {error}"
        )

        failed_files.append(
            {
                "File": input_file,
                "Error": str(error),
            }
        )

        print(
            "\nContinuing with the next file..."
        )


# ============================================================
# SAVE PROCESSING ERRORS
# ============================================================

if failed_files:

    errors_file = os.path.join(
        OUTPUT_FOLDER,
        "processing_errors.csv",
    )

    errors_df = pd.DataFrame(
        failed_files,
        columns=[
            "File",
            "Error",
        ],
    )

    errors_df.to_csv(
        errors_file,
        index=False,
        encoding="utf-8-sig",
    )


# ============================================================
# FINAL SUMMARY
# ============================================================

print("\n\n")
print("===================================")
print("PROCESSING COMPLETE")
print("===================================")

print(
    f"Input files found:      {len(input_files)}"
)

print(
    f"Files processed:        {len(successful_files)}"
)

print(
    f"Files with errors:      {len(failed_files)}"
)

print(
    f"Output folder:          {OUTPUT_FOLDER}"
)


if successful_files:

    print("\nSuccessfully processed:")

    for file in successful_files:

        print(
            f"  OK: {file}"
        )


if failed_files:

    print("\nFiles with errors:")

    for item in failed_files:

        print(
            f"  ERROR: {item['File']}"
        )

        print(
            f"         {item['Error']}"
        )

    print(
        "\nDetailed errors saved to:"
    )

    print(
        f"  {os.path.join(OUTPUT_FOLDER, 'processing_errors.csv')}"
    )


print("\n===================================")
print("DONE")
print("===================================")
