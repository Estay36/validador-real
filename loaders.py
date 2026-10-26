"""
Lectura y estandarización de las fuentes:

  1. Archivo "CARGAS MEDIOS" (pestañas moradas):
       - PROVISORIOS ............ extracción SAP de Solped/Pedidos (la que envía Henry)
       - Monitor Prov ........... archivo de carga masiva a SAP (trae PEP y texto largo)
       - Recepción PROVISORIOS .. respaldo histórico de lo ya subido a SAP
       - Aprobadores ............ maestro marca -> código PEP -> responsable
  2. Informe Real de Inversión (hoja "REAL <MES> <AÑO>" o "BASES <AÑO>").

Cada función devuelve un DataFrame con nombres de columna internos (snake_case)
y conserva el número de fila de origen para trazabilidad.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

import config as cfg
from utils import (
    a_entero_id, a_fecha, a_numero, buscar_hoja, codigo_marca_pep, columna,
    limpiar_columnas, normalizar,
)


class ErrorEstructura(Exception):
    """La planilla no tiene la estructura esperada."""


def _leer_hoja(archivo, objetivo: str, **kwargs) -> pd.DataFrame:
    xls = pd.ExcelFile(archivo)
    hoja = buscar_hoja(xls.sheet_names, objetivo)
    if hoja is None:
        raise ErrorEstructura(
            f"No se encontró la pestaña '{objetivo}'. Pestañas disponibles: "
            f"{', '.join(xls.sheet_names)}"
        )
    return pd.read_excel(xls, sheet_name=hoja, dtype=object, **kwargs)


def _exigir(df: pd.DataFrame, nombre_hoja: str, *cols: str) -> dict[str, str]:
    encontrados, faltantes = {}, []
    for c in cols:
        real = columna(df, c)
        if real is None:
            faltantes.append(c)
        else:
            encontrados[c] = real
    if faltantes:
        raise ErrorEstructura(
            f"En '{nombre_hoja}' faltan las columnas: {', '.join(faltantes)}"
        )
    return encontrados


# ---------------------------------------------------------------------------
# PROVISORIOS
# ---------------------------------------------------------------------------
def leer_provisorios(archivo) -> pd.DataFrame:
    df = limpiar_columnas(_leer_hoja(archivo, cfg.HOJA_PROVISORIOS))
    c = _exigir(
        df, cfg.HOJA_PROVISORIOS,
        "SOLPED", "PEDIDO", "Pos.solicitud pedido", "Texto breve", "Valor total",
        "Moneda", "Centro", "Proveedor fijo", "Nombre de proveedor",
        "Fecha de solicitud",
    )
    col_coment = columna(df, "RECEPCIÓN / COMENTARIO", "RECEPCION / COMENTARIO", "RECEPCIÓN")
    col_status = columna(df, "Status tratamiento")
    col_aprob = columna(df, "Solicitante (Aprobador)")
    col_hoja = columna(df, "Hoja de entrada")
    col_fped = columna(df, "Fecha de pedido")       # si algún día viene en la extracción

    out = pd.DataFrame({
        "fila_origen": df.index + 2,
        "solped": df[c["SOLPED"]].map(a_entero_id),
        "pos": df[c["Pos.solicitud pedido"]].map(a_entero_id),
        "pedido": df[c["PEDIDO"]].map(a_entero_id),
        "pedido_txt": df[c["PEDIDO"]].astype(str).str.strip(),
        "texto_breve": df[c["Texto breve"]].astype(str).str.strip(),
        "valor_prov": df[c["Valor total"]].map(a_numero),
        "moneda": df[c["Moneda"]].astype(str).str.strip().str.upper(),
        "centro": df[c["Centro"]].map(lambda v: "" if pd.isna(v) else str(a_entero_id(v) or v).strip()),
        "proveedor_fijo": df[c["Proveedor fijo"]].map(a_entero_id),
        "nombre_proveedor": df[c["Nombre de proveedor"]].astype(str).str.strip(),
        "fecha_solicitud": df[c["Fecha de solicitud"]].map(a_fecha),
        "fecha_pedido": df[col_fped].map(a_fecha) if col_fped else None,
        "status_trat": df[col_status].astype(str).str.strip() if col_status else "",
        "aprobador_sap": df[col_aprob].astype(str).str.strip() if col_aprob else "",
        "comentario": df[col_coment].fillna("").astype(str).str.strip() if col_coment else "",
        "hoja_entrada_txt": df[col_hoja].fillna("").astype(str).str.strip() if col_hoja else "",
    })
    out = out[out["solped"].notna()].reset_index(drop=True)
    out["mes_texto"] = out["texto_breve"].map(mes_desde_texto_breve)
    return out


def mes_desde_texto_breve(texto: str) -> int | None:
    """'Mjul Cristal TVA C5' -> 7. El prefijo M+mes lo pone la carga provisoria."""
    m = re.match(r"^\s*M([a-zA-Z]{3})", str(texto))
    if not m:
        return None
    abrev = m.group(1).lower()
    for num, (_, _, ab) in cfg.MESES.items():
        if ab == abrev:
            return num
    return None


# ---------------------------------------------------------------------------
# Monitor Prov
# ---------------------------------------------------------------------------
def leer_monitor_prov(archivo) -> pd.DataFrame:
    df = limpiar_columnas(_leer_hoja(archivo, cfg.HOJA_MONITOR_PROV))
    c = _exigir(
        df, cfg.HOJA_MONITOR_PROV,
        "NRO DOC", "LINEA", "TEXTO", "ELEM PEP", "CANTIDAD SERV", "PRECIO GR",
    )
    col_estado = columna(df, "ESTADO")
    col_msj = columna(df, "Mensaje")
    col_serv = columna(df, "SERVICIO")
    col_prov = columna(df, "PROVEEDOR")
    col_sox = columna(df, "SOX")
    col_ref = columna(df, "REF EXTERNA")
    col_mon = columna(df, "MONEDA")

    cant = df[c["CANTIDAD SERV"]].map(a_numero)
    precio = df[c["PRECIO GR"]].map(a_numero).fillna(1.0)
    out = pd.DataFrame({
        "fila_monitor": df.index + 2,
        "nro_doc": df[c["NRO DOC"]].map(a_entero_id),
        "linea": df[c["LINEA"]].map(a_entero_id),
        "texto_largo": df[c["TEXTO"]].fillna("").astype(str).str.strip(),
        "pep": df[c["ELEM PEP"]].fillna("").astype(str).str.strip(),
        "monto_monitor": cant * precio,
        "servicio": df[col_serv].map(a_entero_id) if col_serv else None,
        "rut_proveedor": df[col_prov].fillna("").astype(str).str.strip() if col_prov else "",
        "sox": df[col_sox].fillna("").astype(str).str.strip() if col_sox else "",
        "ref_externa": df[col_ref].fillna("").astype(str).str.strip() if col_ref else "",
        "estado": df[col_estado].fillna("").astype(str).str.strip().str.upper() if col_estado else "S",
        "mensaje": df[col_msj].fillna("").astype(str).str.strip() if col_msj else "",
        "moneda_monitor": df[col_mon].fillna("").astype(str).str.strip() if col_mon else "",
    })
    out = out[out["nro_doc"].notna()]
    # Líneas marcadas como eliminadas/duplicadas en el monitor no generan posición
    eliminada = out["mensaje"].str.upper().str.contains("ELIMIN", na=False)
    return out[~eliminada].drop_duplicates(["nro_doc", "linea"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Recepción PROVISORIOS existente (histórico)
# ---------------------------------------------------------------------------
def leer_recepcion_existente(archivo) -> pd.DataFrame:
    try:
        df = limpiar_columnas(_leer_hoja(archivo, cfg.HOJA_RECEPCION_PROV))
    except ErrorEstructura:
        return pd.DataFrame(columns=["solped", "pos", "documento_material", "pep_hist", "sociedad_hist"])
    c = _exigir(df, cfg.HOJA_RECEPCION_PROV, "Solicitud de pedido", "Posición de pedido")
    col_doc = columna(df, "Documento material", "Documento")
    col_pep = columna(df, "Elemento PEP")
    col_soc = columna(df, "Sociedad")
    col_fped = columna(df, "Fecha de pedido")
    out = pd.DataFrame({
        "solped": df[c["Solicitud de pedido"]].map(a_entero_id),
        "pos": df[c["Posición de pedido"]].map(a_entero_id),
        "documento_material": df[col_doc].map(a_entero_id) if col_doc else None,
        "pep_hist": df[col_pep].fillna("").astype(str).str.strip() if col_pep else "",
        "sociedad_hist": df[col_soc].fillna("").astype(str).str.strip() if col_soc else "",
        "fecha_pedido_hist": df[col_fped].map(a_fecha) if col_fped else None,
    })
    out = out[out["solped"].notna() & out["pos"].notna()]
    return out.drop_duplicates(["solped", "pos"], keep="last").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Aprobadores (maestro de marcas)
# ---------------------------------------------------------------------------
def leer_aprobadores(archivo) -> pd.DataFrame:
    """
    Columnas A:H de la pestaña Aprobadores: UEN, APROBADOR, CENTRO, COD.,
    MARCA, PEP (prefijo), código de marca y, en la columna H, el nombre del
    responsable de recepción al inicio de cada bloque (se propaga hacia abajo).
    """
    try:
        raw = _leer_hoja(archivo, cfg.HOJA_APROBADORES, header=None)
    except ErrorEstructura:
        return pd.DataFrame(columns=["uen", "aprobador", "centro", "marca", "codigo_marca", "responsable"])
    raw = raw.iloc[:, :8]
    raw.columns = ["uen", "aprobador", "centro", "cod_aprob", "marca", "pep_prefijo", "codigo_marca", "responsable"]
    raw = raw.iloc[1:]
    raw["responsable"] = raw["responsable"].map(lambda v: str(v).strip().upper() if pd.notna(v) and str(v).strip() else None)
    raw["responsable"] = raw["responsable"].ffill()
    raw = raw[raw["marca"].notna() & raw["codigo_marca"].notna()].copy()
    raw["codigo_marca"] = raw["codigo_marca"].astype(str).str.replace(".", "", regex=False).str.strip().str.upper()
    raw["marca"] = raw["marca"].astype(str).str.strip()
    raw["marca_norm"] = raw["marca"].map(normalizar)
    raw["centro"] = raw["centro"].map(lambda v: str(a_entero_id(v)) if a_entero_id(v) is not None else "")
    return raw.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Informe Real
# ---------------------------------------------------------------------------
@dataclass
class InformeReal:
    datos: pd.DataFrame
    hoja: str
    mes: int | None
    anio: int | None


def _mes_desde_nombre(texto: str) -> tuple[int | None, int | None]:
    t = normalizar(texto)
    mes = None
    for num, (ab, largo, _) in cfg.MESES.items():
        if re.search(rf"\b({largo}|{ab})\b", t):
            mes = num
            break
    anio = re.search(r"\b(20\d{2})\b", t)
    return mes, (int(anio.group(1)) if anio else None)


def hojas_informe_real(archivo) -> list[str]:
    """Hojas candidatas: 'REAL <MES> <AÑO>' (con datos) y 'BASES <AÑO>'."""
    xls = pd.ExcelFile(archivo)
    candidatas = []
    for h in xls.sheet_names:
        n = normalizar(h)
        if n.startswith("REAL ") and _mes_desde_nombre(h)[0] and "ACUM" not in n:
            candidatas.append(h)
    candidatas += [h for h in xls.sheet_names if normalizar(h).startswith(cfg.HOJA_BASES_REAL)]
    return candidatas


def leer_informe_real(archivo, hoja: str | None = None, mes: int | None = None) -> InformeReal:
    xls = pd.ExcelFile(archivo)
    if hoja is None:
        cands = hojas_informe_real(archivo)
        if not cands:
            raise ErrorEstructura("El Informe Real no tiene hojas 'REAL <MES>' ni 'BASES'.")
        hoja = cands[0]

    raw = pd.read_excel(xls, sheet_name=hoja, header=None, dtype=object)
    # Detectar la fila de encabezado (la que contiene "Monto Neto Real")
    fila_enc = None
    for i in range(min(40, len(raw))):
        fila = [normalizar(v) for v in raw.iloc[i].tolist()]
        if "MONTO NETO REAL" in fila:
            fila_enc = i
            break
    if fila_enc is None:
        raise ErrorEstructura(f"No se encontró el encabezado 'Monto Neto Real' en la hoja '{hoja}'.")

    df = raw.iloc[fila_enc + 1:].copy()
    df.columns = [str(v).strip() if pd.notna(v) else f"col_{j}" for j, v in enumerate(raw.iloc[fila_enc])]
    df["fila_informe"] = df.index + 1
    df = df.dropna(how="all", subset=[c for c in df.columns if c != "fila_informe"])

    es_base = columna(df, "MARCA") is not None and columna(df, "Pinta") is None
    if es_base:
        c = _exigir(df, hoja, "MES", "MARCA", "MEDIO", "VEHICULO", "MONTO NETO REAL")
        col = {
            "pinta": c["MARCA"], "medio": c["MEDIO"], "vehiculo": c["VEHICULO"],
            "monto": c["MONTO NETO REAL"],
            "burst": columna(df, "BURST"), "tipo": columna(df, "TIPO COMPRA"),
            "empresa": columna(df, "UEN"), "rut": columna(df, "RUT MEDIO"),
            "razon_social": columna(df, "RAZÓN SOCIAL MEDIO", "RAZON SOCIAL MEDIO"),
            "id_medio": None,
        }
    else:
        c = _exigir(df, hoja, "Pinta", "Medio", "Proveedor-Vehiculo", "Monto Neto Real")
        col = {
            "pinta": c["Pinta"], "medio": c["Medio"], "vehiculo": c["Proveedor-Vehiculo"],
            "monto": c["Monto Neto Real"],
            "burst": columna(df, "Burst"), "tipo": columna(df, "Tipo"),
            "empresa": columna(df, "EMPRESA"), "rut": columna(df, "RUT"),
            "razon_social": columna(df, "Empresa") if columna(df, "Empresa") != columna(df, "EMPRESA") else None,
            "id_medio": columna(df, "ID Medio"),
        }
        # "EMPRESA" (UEN) y "Empresa" (razón social del medio) difieren solo en
        # mayúsculas: se toman por posición para no confundirlas.
        cols_emp = [x for x in df.columns if normalizar(x) == "EMPRESA"]
        if len(cols_emp) >= 2:
            col["empresa"], col["razon_social"] = cols_emp[0], cols_emp[-1]

    def _txt(nombre):
        return df[col[nombre]].fillna("").astype(str).str.strip() if col.get(nombre) else ""

    out = pd.DataFrame({
        "fila_informe": df["fila_informe"],
        "pinta": _txt("pinta"),
        "id_medio": _txt("id_medio"),
        "medio": _txt("medio").map(normalizar),
        "vehiculo": _txt("vehiculo"),
        "burst": _txt("burst"),
        "tipo": _txt("tipo"),
        "empresa": _txt("empresa"),
        "rut": _txt("rut"),
        "razon_social": _txt("razon_social"),
        "monto_real": df[col["monto"]].map(a_numero),
    })
    if es_base:
        mes_col = columna(df, "MES")
        out["mes"] = df[mes_col].map(lambda v: _mes_desde_nombre(str(v))[0])
    out = out[(out["pinta"] != "") & out["monto_real"].notna()]

    mes_hoja, anio_hoja = _mes_desde_nombre(hoja)
    if es_base:
        if mes is None:
            mes = int(out["mes"].max()) if out["mes"].notna().any() else None
        out = out[out["mes"] == mes]
    else:
        mes = mes or mes_hoja
    return InformeReal(datos=out.reset_index(drop=True), hoja=hoja, mes=mes, anio=anio_hoja)
