"""
Funciones utilitarias: lectura robusta de números y fechas que vienen
pegadas desde SAP (como texto con formato chileno), normalización de textos
y similitud difusa.
"""
from __future__ import annotations

import datetime as dt
import math
import re
import unicodedata

import pandas as pd

try:
    from rapidfuzz import fuzz as _fuzz
except ImportError:  # pragma: no cover - respaldo si no está instalado
    _fuzz = None
    from difflib import SequenceMatcher


# ---------------------------------------------------------------------------
# Números
# ---------------------------------------------------------------------------
_PATRON_MILES = re.compile(r"^\d{1,3}(\.\d{3})+$")


def a_numero(valor) -> float | None:
    """
    Convierte a float valores numéricos que pueden venir como:
      - número (float/int)
      - texto con formato chileno: '1.222.445', '4.985,00', '100,16'
      - texto con signo al final, como lo exporta SAP: '116.049,00-'
    Devuelve None si no es interpretable.
    """
    if valor is None:
        return None
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        if isinstance(valor, float) and math.isnan(valor):
            return None
        return float(valor)
    s = str(valor).strip().replace("$", "").replace(" ", "").replace(" ", "")
    if not s:
        return None
    negativo = s.startswith("-") or s.endswith("-")
    s = s.strip("-")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif _PATRON_MILES.match(s):
        s = s.replace(".", "")
    try:
        x = float(s)
    except ValueError:
        return None
    return -x if negativo else x


def a_entero_id(valor) -> int | None:
    """Identificadores SAP (Solped, Pedido, posición) como entero."""
    x = a_numero(valor)
    if x is None:
        return None
    return int(round(x))


# ---------------------------------------------------------------------------
# Fechas
# ---------------------------------------------------------------------------
def a_fecha(valor) -> dt.date | None:
    """
    Acepta datetime, número serial de Excel (46239) o texto 'dd.mm.aaaa' /
    'dd-mm-aaaa' / 'dd/mm/aaaa'.
    """
    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return None
    if isinstance(valor, pd.Timestamp):
        return None if pd.isna(valor) else valor.date()
    if isinstance(valor, dt.datetime):
        return valor.date()
    if isinstance(valor, dt.date):
        return valor
    if isinstance(valor, (int, float)):
        if 20000 < valor < 80000:
            return (dt.datetime(1899, 12, 30) + dt.timedelta(days=float(valor))).date()
        return None
    s = str(valor).strip()
    m = re.match(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{4})", s)
    if m:
        d, mth, y = map(int, m.groups())
        try:
            return dt.date(y, mth, d)
        except ValueError:
            return None
    try:
        return pd.to_datetime(s, dayfirst=True).date()
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Textos
# ---------------------------------------------------------------------------
def normalizar(texto) -> str:
    """Mayúsculas, sin acentos, solo letras/números separados por un espacio."""
    if texto is None or (isinstance(texto, float) and math.isnan(texto)):
        return ""
    s = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    s = s.upper().replace("&", " Y ")
    s = re.sub(r"[^A-Z0-9+]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def normalizar_nombre_hoja(nombre: str) -> str:
    return normalizar(nombre).replace(" ", "")


def buscar_hoja(nombres: list[str], objetivo: str) -> str | None:
    """Devuelve el nombre real de la hoja que coincide con `objetivo`."""
    obj = normalizar_nombre_hoja(objetivo)
    for n in nombres:
        if normalizar_nombre_hoja(n) == obj:
            return n
    return None


def limpiar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    """Quita espacios sobrantes de los encabezados ('SOLPED ' -> 'SOLPED')."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def columna(df: pd.DataFrame, *candidatos: str) -> str | None:
    """Ubica una columna por nombre normalizado (tolera acentos/espacios)."""
    mapa = {normalizar(c): c for c in df.columns}
    for cand in candidatos:
        c = mapa.get(normalizar(cand))
        if c is not None:
            return c
    return None


def codigo_marca_pep(pep) -> str:
    """
    'M.26.A90.FGATO.11131' -> 'FGATO'.  Normaliza los códigos de la pestaña
    Aprobadores que vienen con punto final ('GKEM_.' -> 'GKEM_').
    """
    if pep is None or (isinstance(pep, float) and math.isnan(pep)):
        return ""
    partes = [p for p in str(pep).strip().split(".") if p]
    if len(partes) >= 4:
        return partes[3].strip().upper()
    return ""


def codigo_medio_pep(pep) -> str:
    if pep is None or (isinstance(pep, float) and math.isnan(pep)):
        return ""
    partes = [p for p in str(pep).strip().split(".") if p]
    return partes[-1].strip() if len(partes) >= 5 else ""


def sociedad_desde_pep(pep) -> str:
    """'M.26.A90.FGATO.11131' -> 'A090' (regla verificada en el 99,8 % del histórico)."""
    if pep is None or (isinstance(pep, float) and math.isnan(pep)):
        return ""
    m = re.search(r"\.?(A)(\d{2})\.", str(pep).upper())
    if not m:
        return ""
    return f"A0{m.group(2)}"


# ---------------------------------------------------------------------------
# Similitud
# ---------------------------------------------------------------------------
def similitud(a: str, b: str) -> float:
    """Similitud 0-100 robusta al orden de palabras y a textos parciales."""
    if not a or not b:
        return 0.0
    if _fuzz is not None:
        return max(_fuzz.token_set_ratio(a, b), 0.9 * _fuzz.partial_ratio(a, b))
    return 100 * SequenceMatcher(None, a, b).ratio()


def tokens_utiles(texto: str, stopwords: set[str]) -> set[str]:
    return {t for t in texto.split() if t not in stopwords and len(t) > 1}
