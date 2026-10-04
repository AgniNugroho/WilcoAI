from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Optional, Union


@dataclass
class ReadbackResult:
    """Outcome of pilot voice readback verification."""
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    matched_items: dict[str, Any] = field(default_factory=dict)
    missing_items: list[str] = field(default_factory=list)


# Single digit translation table (English + Indonesian)
DIGIT_WORDS: dict[str, str] = {
    # English standard & aviation phonetic
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "tree": "3",
    "four": "4",
    "fower": "4",
    "five": "5",
    "fife": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "ait": "8",
    "nine": "9",
    "niner": "9",
    # Indonesian
    "kosong": "0",
    "nol": "0",
    "satu": "1",
    "dua": "2",
    "tiga": "3",
    "empat": "4",
    "lima": "5",
    "enam": "6",
    "tujuh": "7",
    "delapan": "8",
    "sembilan": "9",
}

# Compound numbers (teens, tens, hundreds, thousands)
NUMBER_WORDS: dict[str, int] = {
    # English
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "hundred": 100,
    "thousand": 1000,
    # Indonesian
    "sepuluh": 10,
    "sebelas": 11,
    "seratus": 100,
    "seribu": 1000,
}

# NATO Phonetic Alphabet words
NATO_PHONETICS: dict[str, str] = {
    "alpha": "A",
    "alfa": "A",
    "bravo": "B",
    "charlie": "C",
    "delta": "D",
    "echo": "E",
    "foxtrot": "F",
    "golf": "G",
    "hotel": "H",
    "india": "I",
    "juliett": "J",
    "juliet": "J",
    "kilo": "K",
    "lima": "L",
    "mike": "M",
    "november": "N",
    "oscar": "O",
    "papa": "P",
    "quebec": "Q",
    "romeo": "R",
    "sierra": "S",
    "tango": "T",
    "uniform": "U",
    "victor": "V",
    "whiskey": "W",
    "xray": "X",
    "x-ray": "X",
    "yankee": "Y",
    "zulu": "Z",
}

# Airline Telephony Designators and Spoken Aliases
AIRLINE_TELEPHONY: dict[str, list[str]] = {
    "GIA": ["garuda", "indonesia", "gia"],
    "GARUDA": ["garuda", "indonesia", "gia"],
    "INDONESIA": ["garuda", "indonesia", "gia"],
    "LNI": ["lion", "lion air", "lni"],
    "LION": ["lion", "lion air", "lni"],
    "CTV": ["citilink", "supergreen", "ctv"],
    "CITILINK": ["citilink", "supergreen", "ctv"],
    "SUPERGREEN": ["citilink", "supergreen", "ctv"],
    "BTK": ["batik", "btk"],
    "BATIK": ["batik", "btk"],
    "AWQ": ["airasia", "wagon air", "awq"],
    "AIRASIA": ["airasia", "wagon air", "awq"],
    "SJY": ["sriwijaya", "sjy"],
    "SRIWIJAYA": ["sriwijaya", "sjy"],
    "SJV": ["super air jet", "sjv"],
}



def normalize_text_and_numbers(text: str) -> str:
    """
    Normalizes spoken pilot transcript by lowercasing, expanding compound numbers
    (e.g. 'five thousand' -> '5000', 'lima ribu' -> '5000'), converting digit words
    (English & Indonesian) to digits, and collapsing contiguous digit runs.
    """
    clean = text.lower()
    # Replace punctuation with spaces
    clean = re.sub(r"[,;:.?!/\\-_]", " ", clean)

    # 1. Expand thousands in English: e.g. "five thousand" -> "5000", "5 thousand" -> "5000"
    for word, digit in [
        ("one", 1), ("two", 2), ("three", 3), ("four", 4), ("five", 5),
        ("six", 6), ("seven", 7), ("eight", 8), ("nine", 9), ("ten", 10),
        ("eleven", 11), ("twelve", 12),
    ]:
        pattern = rf"\b{word}\s+thousand\b"
        clean = re.sub(pattern, str(digit * 1000), clean)

    clean = re.sub(r"\b(\d+)\s+thousand\b", lambda m: str(int(m.group(1)) * 1000), clean)

    # 2. Expand thousands in Indonesian: e.g. "lima ribu" -> "5000", "seribu" -> "1000"
    clean = re.sub(r"\bseribu\b", "1000", clean)
    for word, digit in [
        ("satu", 1), ("dua", 2), ("tiga", 3), ("empat", 4), ("lima", 5),
        ("enam", 6), ("tujuh", 7), ("delapan", 8), ("sembilan", 9), ("sepuluh", 10),
        ("sebelas", 11), ("dua belas", 12),
    ]:
        pattern = rf"\b{word}\s+ribu\b"
        clean = re.sub(pattern, str(digit * 1000), clean)

    clean = re.sub(r"\b(\d+)\s+ribu\b", lambda m: str(int(m.group(1)) * 1000), clean)

    # 3. Word token mapping and collapsing
    raw_tokens = clean.split()
    processed_tokens: list[str] = []

    for tok in raw_tokens:
        if tok in DIGIT_WORDS:
            processed_tokens.append(DIGIT_WORDS[tok])
        elif tok in NUMBER_WORDS:
            processed_tokens.append(str(NUMBER_WORDS[tok]))
        else:
            processed_tokens.append(tok)

    # 4. Collapse adjacent single-digit tokens: e.g. ['1', '0', '1', '1'] -> '1011'
    collapsed_tokens: list[str] = []
    digit_buffer: list[str] = []

    for tok in processed_tokens:
        if len(tok) == 1 and tok.isdigit():
            digit_buffer.append(tok)
        else:
            if digit_buffer:
                collapsed_tokens.append("".join(digit_buffer))
                digit_buffer = []
            collapsed_tokens.append(tok)

    if digit_buffer:
        collapsed_tokens.append("".join(digit_buffer))

    result = " ".join(collapsed_tokens)

    # 5. Normalize runway designators Left / Right / Center (English and Indonesian)
    # e.g. "25 left" -> "25l", "25 kiri" -> "25l", "25 right" -> "25r", "25 center" -> "25c"
    result = re.sub(r"\b(\d{1,2})\s*(?:left|kiri)\b", r"\g<1>l", result)
    result = re.sub(r"\b(\d{1,2})\s*(?:right|kanan)\b", r"\g<1>r", result)
    result = re.sub(r"\b(\d{1,2})\s*(?:center|centre|tengah)\b", r"\g<1>c", result)

    return result



def expand_nato_to_letters(text: str) -> str:
    """Convert NATO phonetic words into uppercase letters for alphanumeric matching."""
    tokens = text.lower().split()
    converted: list[str] = []
    for tok in tokens:
        if tok in NATO_PHONETICS:
            converted.append(NATO_PHONETICS[tok])
        else:
            converted.append(tok)
    return " ".join(converted)


def verify_readback(pilot_text: str, expected_items: dict[str, Any]) -> ReadbackResult:
    """
    Validates pilot voice readback against expected ATC clearance parameters.
    Supports English & Indonesian bilingual numbers and phrasing.

    Supported expected items:
    - `qnh`: int / float / str (e.g. 1011, "1011")
    - `squawk`: str / int (e.g. "5201")
    - `runway`: str (e.g. "11", "29", "RW11")
    - `sid`: str (e.g. "CA2L", "ELANG1")
    - `hold_short`: str / bool (e.g. "11", True)
    - `alt` / `altitude` / `target_alt_ft`: int (e.g. 5000)
    - `callsign`: str (e.g. "GIA123")
    """
    errors: list[str] = []
    matched_items: dict[str, Any] = {}
    missing_items: list[str] = []

    if not pilot_text or not pilot_text.strip():
        return ReadbackResult(
            is_valid=False,
            errors=["Pilot transmission is empty or silent"],
            matched_items={},
            missing_items=list(expected_items.keys()),
        )

    norm = normalize_text_and_numbers(pilot_text)
    nato_expanded = expand_nato_to_letters(pilot_text)

    # -------------------------------------------------------------------------
    # 1. QNH / Altimeter Verification
    # -------------------------------------------------------------------------
    qnh_key = next((k for k in ("qnh", "altimeter", "qnh_hpa") if k in expected_items), None)
    if qnh_key is not None:
        expected_qnh_val = expected_items[qnh_key]
        try:
            expected_qnh_int = int(float(expected_qnh_val))
        except (ValueError, TypeError):
            expected_qnh_int = 1013

        # Look for explicit QNH keyword: e.g. "qnh 1011", "altimeter 1011", "tekanan 1011"
        qnh_match = re.search(
            r"\b(?:qnh|altimeter|pressure|tekanan)\s*(?:is\s*)?(\d{4})\b",
            norm,
        )

        found_qnh: Optional[int] = None
        if qnh_match:
            found_qnh = int(qnh_match.group(1))
        else:
            # Fallback: look for 4-digit pressure in standard barometric range (940..1060 or 2800..3100)
            # that is distinct from squawk
            squawk_val_str = str(expected_items.get("squawk", ""))
            four_digits = re.findall(r"\b(\d{4})\b", norm)
            for fd in four_digits:
                val = int(fd)
                if (940 <= val <= 1060 or 2800 <= val <= 3100) and fd != squawk_val_str:
                    found_qnh = val
                    break

        if found_qnh is not None:
            if found_qnh == expected_qnh_int:
                matched_items[qnh_key] = found_qnh
            else:
                errors.append(f"QNH mismatch: expected {expected_qnh_int}, got {found_qnh}")
        else:
            missing_items.append(qnh_key)

    # -------------------------------------------------------------------------
    # 2. Squawk Transponder Verification
    # -------------------------------------------------------------------------
    squawk_key = next((k for k in ("squawk", "assigned_squawk", "transponder") if k in expected_items), None)
    if squawk_key is not None:
        expected_squawk = str(expected_items[squawk_key]).strip().zfill(4)

        # Look for explicit squawk keyword: "squawk 5201", "transponder 5201", "squawk 5280"
        sq_match = re.search(r"\b(?:squawk|transponder|beacon)\s*(\d{4})\b", norm)
        found_squawk: Optional[str] = None

        if sq_match:
            found_squawk = sq_match.group(1)
        else:
            # Fallback: look for 4-digit number that is NOT the QNH value
            qnh_val_str = str(matched_items.get(qnh_key if qnh_key else "", expected_items.get("qnh", "")))
            four_digits = re.findall(r"\b(\d{4})\b", norm)
            for fd in four_digits:
                if fd != qnh_val_str:
                    found_squawk = fd
                    break

        if found_squawk is not None:
            if found_squawk == expected_squawk:
                matched_items[squawk_key] = found_squawk
            else:
                errors.append(f"Squawk mismatch: expected {expected_squawk}, got {found_squawk}")
        else:
            missing_items.append(squawk_key)


    # -------------------------------------------------------------------------
    # 3. Runway Verification
    # -------------------------------------------------------------------------
    runway_key = next((k for k in ("runway", "assigned_runway", "rwy") if k in expected_items), None)
    if runway_key is not None:
        raw_exp_rwy = str(expected_items[runway_key]).upper().replace("RWY", "").replace("RW", "").strip()
        # Look for explicit runway phrasing: "runway 11", "landas pacu 11", "landasan 11"
        rwy_match = re.search(
            r"\b(?:runway|rwy|rw|landas\s*pacu|landasan)\s*(\d{1,2}[lcr]?)\b",
            norm,
        )

        found_rwy: Optional[str] = None
        if rwy_match:
            found_rwy = rwy_match.group(1).upper()
        else:
            # Check if runway digits appear as isolated token
            isolated = re.findall(r"\b(\d{1,2}[LCR]?)\b", norm.upper())
            for candidate in isolated:
                if candidate == raw_exp_rwy or candidate.lstrip("0") == raw_exp_rwy.lstrip("0"):
                    found_rwy = candidate
                    break

        if found_rwy is not None:
            clean_found = found_rwy.lstrip("0")
            clean_exp = raw_exp_rwy.lstrip("0")
            if clean_found == clean_exp:
                matched_items[runway_key] = raw_exp_rwy
            else:
                errors.append(f"Runway mismatch: expected {raw_exp_rwy}, got {found_rwy}")
        else:
            missing_items.append(runway_key)

    # -------------------------------------------------------------------------
    # 4. SID / Departure Routing Verification
    # -------------------------------------------------------------------------
    sid_key = next((k for k in ("sid", "cleared_sid", "departure") if k in expected_items), None)
    if sid_key is not None:
        expected_sid = str(expected_items[sid_key]).strip().upper()
        # Clean expected SID for comparison (e.g. "CA2L")
        clean_sid = re.sub(r"\s+", "", expected_sid)

        # Check in raw norm, or collapsed NATO-expanded tokens
        norm_no_spaces = re.sub(r"\s+", "", norm.upper())
        nato_no_spaces = re.sub(r"\s+", "", nato_expanded.upper())

        # Also check if words in SID are matched
        matched_sid = False
        if clean_sid in norm_no_spaces or clean_sid in nato_no_spaces:
            matched_sid = True
        else:
            # Check if pilot spoke words like "charlie alpha 2 lima"
            # Normalize NATO words in pilot text and check
            nato_tokens = [NATO_PHONETICS.get(w.lower(), w.upper()) for w in pilot_text.split()]
            collapsed_nato = "".join(nato_tokens)
            if clean_sid in collapsed_nato:
                matched_sid = True

        if matched_sid:
            matched_items[sid_key] = expected_sid
        else:
            # Check if pilot mentioned an incorrect SID
            sid_candidates = re.findall(r"\b([A-Za-z]{2,6}\d[A-Za-z]?)\b", pilot_text.upper())
            other_sids = [s for s in sid_candidates if s != clean_sid]
            if other_sids:
                errors.append(f"SID mismatch: expected {expected_sid}, got {other_sids[0]}")
            else:
                missing_items.append(sid_key)

    # -------------------------------------------------------------------------
    # 5. Hold Short Instructions Verification
    # -------------------------------------------------------------------------
    hold_key = next((k for k in ("hold_short", "holding_short") if k in expected_items), None)
    if hold_key is not None:
        expected_hold = str(expected_items[hold_key]).upper().replace("RWY", "").replace("RW", "").strip()

        hold_match = re.search(
            r"\b(?:holding\s*short|hold\s*short|tahan\s*sebelum|menunggu\s*sebelum)\s*(?:of\s*)?(?:the\s*)?(?:runway|rwy|rw|landas\s*pacu|landasan)?\s*(\d{1,2}[lcr]?)?\b",
            norm,
        )

        if hold_match:
            found_hold_rwy = hold_match.group(1)
            if expected_hold in ("TRUE", "1", ""):
                # Any hold short acknowledged
                matched_items[hold_key] = True
            elif found_hold_rwy:
                clean_found = found_hold_rwy.upper().lstrip("0")
                clean_exp = expected_hold.lstrip("0")
                if clean_found == clean_exp:
                    matched_items[hold_key] = expected_hold
                else:
                    errors.append(
                        f"Hold short runway mismatch: expected {expected_hold}, got {found_hold_rwy.upper()}"
                    )
            else:
                # Bare "holding short" without runway identifier when specific runway was required
                errors.append(
                    f"Hold short runway omitted: expected runway {expected_hold}"
                )
        else:
            missing_items.append(hold_key)

    # -------------------------------------------------------------------------
    # 6. Altitude / Flight Level Verification
    # -------------------------------------------------------------------------
    alt_key = next((k for k in ("alt", "altitude", "target_alt_ft") if k in expected_items), None)
    if alt_key is not None:
        expected_alt = int(expected_items[alt_key])

        # Check for climb/maintain phrasing or altitude numbers
        alt_match = re.search(
            r"\b(?:climb|maintain|altitude|alt|naik|ketinggian)\s*(?:to\s*)?(?:and\s*maintain\s*)?(\d{3,5})\b",
            norm,
        )

        found_alt: Optional[int] = None
        if alt_match:
            found_alt = int(alt_match.group(1))
        else:
            # Check for numbers >= 1000 in text (excluding QNH / squawk)
            candidates = [int(n) for n in re.findall(r"\b(\d{3,5})\b", norm)]
            qnh_num = matched_items.get("qnh")
            for c in candidates:
                if c != qnh_num and c % 500 == 0:
                    found_alt = c
                    break

        if found_alt is not None:
            if found_alt == expected_alt:
                matched_items[alt_key] = found_alt
            else:
                errors.append(f"Altitude mismatch: expected {expected_alt}, got {found_alt}")
        else:
            missing_items.append(alt_key)

    # -------------------------------------------------------------------------
    # 7. Callsign Verification
    # -------------------------------------------------------------------------
    callsign_key = next((k for k in ("callsign", "flight_callsign") if k in expected_items), None)
    if callsign_key is not None:
        expected_cs = str(expected_items[callsign_key]).strip().upper()
        # Parse expected callsign into alpha prefix and digits
        # e.g. "GIA123" -> prefix "GIA", digits "123"
        # e.g. "GARUDA 123" -> prefix "GARUDA", digits "123"
        # e.g. "PK-LION" -> prefix "PK", "LION"
        m_exp = re.match(r"^([A-Z\-]+)\s*(\d+)?([A-Z]+)?$", expected_cs)
        exp_prefix = m_exp.group(1).replace("-", "") if m_exp else expected_cs
        exp_digits = m_exp.group(2) if m_exp and m_exp.group(2) else ""

        acceptable_names = list(AIRLINE_TELEPHONY.get(exp_prefix, [exp_prefix.lower()]))
        if exp_prefix.lower() not in acceptable_names:
            acceptable_names.append(exp_prefix.lower())

        cs_candidates = re.findall(r"\b([a-z]+)\s*(\d{1,4}[a-z]?)\b", norm)
        reg_candidates = re.findall(r"\b(pk\s*[-a-z0-9]+)\b", norm)

        matched_cs = False
        mismatch_found: Optional[str] = None

        clean_exp_cs = expected_cs.replace("-", "").replace(" ", "").lower()
        clean_norm = norm.replace("-", "").replace(" ", "").lower()
        if clean_exp_cs in clean_norm:
            matched_cs = True

        ignored_keywords = {
            "runway", "rwy", "rw", "landas", "landasan", "pacu",
            "qnh", "altimeter", "squawk", "transponder", "beacon",
            "climb", "maintain", "wind", "heading", "ketinggian", "tekanan",
        }

        if not matched_cs and exp_digits:
            for airline, num in cs_candidates:
                if airline in ignored_keywords:
                    continue
                airline_matches = any(alias == airline for alias in acceptable_names)
                digits_match = (num == exp_digits)

                if airline_matches and digits_match:
                    matched_cs = True
                    break
                elif airline_matches and not digits_match:
                    mismatch_found = f"{airline.title()} {num}"
                elif not airline_matches and digits_match:
                    mismatch_found = f"{airline.title()} {num}"
                elif not airline_matches and not digits_match:
                    if airline in AIRLINE_TELEPHONY or airline in ("lion", "citilink", "batik", "airasia", "garuda"):
                        mismatch_found = f"{airline.title()} {num}"

        if not matched_cs and not mismatch_found:
            for reg in reg_candidates:
                clean_reg = reg.replace(" ", "").replace("-", "")
                if clean_reg == clean_exp_cs:
                    matched_cs = True
                    break
                else:
                    mismatch_found = reg.upper()

        if matched_cs:
            matched_items[callsign_key] = expected_cs
        elif mismatch_found:
            errors.append(f"Callsign mismatch: expected {expected_cs}, got {mismatch_found}")
        else:
            missing_items.append(callsign_key)

    is_valid = len(errors) == 0 and len(missing_items) == 0
    return ReadbackResult(
        is_valid=is_valid,
        errors=errors,
        matched_items=matched_items,
        missing_items=missing_items,
    )

