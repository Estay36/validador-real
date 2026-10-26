"""
Orquestación: selección de líneas del mes, enlace con Monitor Prov, cruce con
Informe Real y armado de las hojas de salida:

  * Recepción PROVISORIOS (29 columnas A:AC, idénticas a la pestaña actual,
    más columnas de trazabilidad del Informe Real a la derecha)
  * GRAL Recepción (hoja Data + una pestaña por responsable)
  * Hojas de control (excluidas, informe sin uso, homologación de marcas)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

import config as cfg
from cruce_real import cruzar_informe_real
from enlace import enlazar_monitor
from utils import codigo_marca_pep, sociedad_desde_pep


@dataclass
class Resultado:
    recepcion: pd.DataFrame
    gral: pd.DataFrame
    gral_por_responsable: dict[str, pd.DataFrame]
    lineas: pd.DataFrame
    excluidas: pd.DataFrame
    informe_sin_uso: pd.DataFrame
    homologacion: pd.DataFrame
    resumen: dict = field(default_factory=dict)
    informe_anotado: pd.DataFrame | None = None   # Informe Real con marca de uso
    informe_total: pd.DataFrame | None = None     # Informe Real del mes, sin anotar


# ---------------------------------------------------------------------------
# Selección
# ---------------------------------------------------------------------------
def seleccionar_lineas(prov: pd.DataFrame, meses: list[int],
                       recepcion_hist: pd.DataFrame,
                       excluir_recepcionadas: bool = True):
    """
    Devuelve (lineas_a_procesar, excluidas). Reglas de exclusión, en orden:
      1. comentario de PROVISORIOS que parte con 'Elim...' (línea eliminada)
      2. sin número de Pedido (la OC aún no existe en SAP)
      3. ya tiene Documento material en la Recepción histórica (proceso terminado)
    """
    base = prov[prov["mes_texto"].isin(meses)].copy()
    base["motivo_exclusion"] = ""

    elim = base["comentario"].str.upper().str.match(cfg.PATRON_ELIMINADA, na=False)
    base.loc[elim, "motivo_exclusion"] = "Eliminada (comentario en PROVISORIOS)"

    sin_ped = base["pedido"].isna() & (base["motivo_exclusion"] == "")
    base.loc[sin_ped, "motivo_exclusion"] = "Sin número de Pedido"

    base["documento_material_hist"] = np.nan
    if recepcion_hist is not None and not recepcion_hist.empty:
        doc = recepcion_hist.dropna(subset=["documento_material"]).set_index(["solped", "pos"])["documento_material"]
        claves = list(zip(base["solped"], base["pos"]))
        base["documento_material_hist"] = [doc.get(k, np.nan) for k in claves]
        if excluir_recepcionadas:
            ya = base["documento_material_hist"].notna() & (base["motivo_exclusion"] == "")
            base.loc[ya, "motivo_exclusion"] = "Ya recepcionada (tiene Documento material)"

    excluidas = base[base["motivo_exclusion"] != ""].copy()
    lineas = base[base["motivo_exclusion"] == ""].drop(columns=["motivo_exclusion"]).copy()
    return lineas, excluidas


# ---------------------------------------------------------------------------
# Hoja Recepción PROVISORIOS
# ---------------------------------------------------------------------------
def _fecha_pedido(row) -> tuple:
    if row.get("fecha_pedido") is not None and not pd.isna(row.get("fecha_pedido")):
        return row["fecha_pedido"], "PROVISORIOS (Fecha de pedido)"
    return row["fecha_solicitud"], "Fecha de solicitud (proxy)"


def armar_recepcion(L: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for _, r in L.iterrows():
        fecha, origen_fecha = _fecha_pedido(r)
        real = r["monto_real"]
        prov = r["valor_prov"]
        q = round(real / prov * 100, 2) if pd.notna(real) and prov else np.nan
        desv = round(real - prov, 2) if pd.notna(real) and pd.notna(prov) else np.nan
        sociedad = sociedad_desde_pep(r["pep"]) or r.get("sociedad_hist", "")
        servicio = r["servicio"] if pd.notna(r.get("servicio")) else cfg.SERVICIO_DEFAULT
        filas.append({
            "Sociedad": sociedad,
            "Texto breve": r["texto_breve"],
            "Proveedor fijo": r["proveedor_fijo"],
            "Nombre de proveedor": r["nombre_proveedor"],
            "Solicitud de pedido": r["solped"],
            "Posición de pedido": r["pos"],
            "Fecha de pedido": fecha,
            "Pedido": r["pedido"],
            "Hoja de entrada": None,
            "Valor total": prov,
            "Moneda": r["moneda"],
            "Documento material": None,
            "Cuenta de mayor": cfg.CUENTA_MAYOR_DEFAULT,
            "Servicio": int(servicio),
            "Importe Contab. HES": real if pd.notna(real) else None,
            "Moneda HES": r["moneda"],
            "Porcentaje de Cumplimiento": q,
            "Desviacion por Posicion": desv,
            "Elemento PEP": r["pep"] or None,
            "Factura": None, "Fecha Factura": None, "Fecha Contab. Factura": None,
            "Fecha Pago": None, "Doc. Pago": None, "Estado Factura": None,
            "Estado Pago": None,
            "Status tratamiento": cfg.STATUS_TRATAMIENTO_DEFAULT,
            "": None,
            "SOX": r["sox"] or None,
            # --- Trazabilidad (a la derecha de la plantilla) ---
            "_Estado cruce": r["estado_cruce"],
            "_Observación": r["observacion"],
            "_Puntaje cruce": r["puntaje_cruce"],
            "_Fila Informe Real": r["fila_informe"],
            "_Pinta": r["inf_pinta"],
            "_ID Medio": r["inf_id_medio"],
            "_Medio": r["inf_medio"],
            "_Proveedor-Vehiculo": r["inf_vehiculo"],
            "_Burst": r["inf_burst"],
            "_Tipo": r["inf_tipo"],
            "_Monto Neto Real": r["monto_informe"],
            "_Texto carga (Monitor)": r["texto_largo"],
            "_Origen PEP": r["origen_pep"],
            "_Origen Fecha de pedido": origen_fecha,
            "_Responsable": r["responsable"],
        })
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# GRAL Recepción
# ---------------------------------------------------------------------------
def _nombre_proveedor_gral(codigo, nombre) -> str:
    cod = "" if codigo is None or pd.isna(codigo) else str(int(codigo))
    return f"{cod}{cfg.SEPARADOR_PROVEEDOR_GRAL}{str(nombre)[:cfg.LARGO_NOMBRE_PROVEEDOR_GRAL]}"


def armar_gral(L: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for _, r in L.iterrows():
        real, prov = r["monto_real"], r["valor_prov"]
        filas.append({
            "Documento compras": str(int(r["pedido"])),
            "Posición": f"{int(r['pos']):05d}",
            "Texto breve": r["texto_breve"],
            "Por entregar (valor)": prov,
            "Nombre de proveedor": _nombre_proveedor_gral(r["proveedor_fijo"], r["nombre_proveedor"]),
            "Centro": r["centro"],
            "Importe a Liberar": real if pd.notna(real) else None,
            "Cantidad a Liberar": real if pd.notna(real) else None,
            "Porcentaje a Liberar": round(real / prov * 100, 2) if pd.notna(real) and prov else None,
            "_Responsable": r["responsable"],
            "_Estado cruce": r["estado_cruce"],
        })
    gral = pd.DataFrame(filas)
    if not gral.empty:
        gral = gral.sort_values(["Documento compras", "Posición"]).reset_index(drop=True)
    return gral


def separar_por_responsable(gral: pd.DataFrame) -> dict[str, pd.DataFrame]:
    salida = {}
    for resp, g in gral.groupby("_Responsable", sort=False):
        nombre = cfg.PESTANAS_RESPONSABLE.get(resp, resp or "Sin responsable")
        salida[nombre] = g.drop(columns=["_Responsable", "_Estado cruce"])
    orden = list(cfg.PESTANAS_RESPONSABLE.values())
    return dict(sorted(salida.items(), key=lambda kv: orden.index(kv[0]) if kv[0] in orden else 99))


# ---------------------------------------------------------------------------
# Responsable
# ---------------------------------------------------------------------------
def asignar_responsable(L: pd.DataFrame, aprobadores: pd.DataFrame) -> list[str]:
    """
    Responsable = etiqueta del bloque de la pestaña Aprobadores donde está la
    marca. Se busca primero por (sociedad del PEP, código de marca), porque
    un mismo código puede repetirse en otro bloque con PEP de otro año/sociedad
    (MANANTIAL M.26.A80 vs. M.25.A81); luego solo por código (primera aparición).
    """
    if aprobadores is None or aprobadores.empty:
        return [""] * len(L)
    por_soc, por_cod = {}, {}
    for pref, cod, resp in zip(aprobadores["pep_prefijo"], aprobadores["codigo_marca"], aprobadores["responsable"]):
        resp = resp if isinstance(resp, str) else ""
        soc = sociedad_desde_pep(f"{pref}X.")
        por_soc.setdefault((soc, cod), resp)
        por_cod.setdefault(cod, resp)
    salida = []
    for pep, cod, cod_txt in zip(L["pep"], L["codigo_marca"], L["codigo_marca_texto"]):
        soc = sociedad_desde_pep(pep)
        salida.append(por_soc.get((soc, cod)) or por_cod.get(cod) or por_cod.get(cod_txt) or "")
    return salida


# ---------------------------------------------------------------------------
# Observaciones
# ---------------------------------------------------------------------------
def _observaciones(L: pd.DataFrame) -> pd.Series:
    obs = [[] for _ in range(len(L))]
    # Vehículo repetido dentro de la misma marca/medio: la asignación entre
    # las líneas repetidas se hizo por cercanía de monto y conviene validarla.
    # Solo se marca si en el grupo repetido hay 2+ líneas cuyo real difiere del
    # provisorio (si todas calzan exacto, no hay ambigüedad posible).
    clave = L["codigo_marca"] + "|" + L["medio_grupo"] + "|" + L["inf_vehiculo"].str.upper().str.strip()
    difiere = (L["monto_real"] - L["valor_prov"]).abs() > cfg.TOLERANCIA_REDONDEO
    rep = clave[(L["inf_vehiculo"] != "") & difiere].value_counts()
    rep = set(rep[rep > 1].index)
    for k, (i, r) in enumerate(L.iterrows()):
        if r["inf_vehiculo"] and clave.loc[i] in rep and difiere.loc[i]:
            obs[k].append("Vehículo repetido con montos distintos: validar asignación entre líneas")
        if pd.notna(r["desviacion_pct"]) and abs(r["desviacion_pct"]) >= cfg.ALERTA_DESVIACION_PCT:
            obs[k].append(f"Desviación {r['desviacion_pct']:+.1f} %")
        if not r["pep"]:
            obs[k].append("Sin Elemento PEP")
        if r["paso_cruce"] == "Paso 2":
            obs[k].append(f"PEP de otra marca ({r['codigo_marca']}) para texto {r['codigo_marca_texto']}")
    return pd.Series(["; ".join(o) for o in obs], index=L.index)


# ---------------------------------------------------------------------------
# Proceso completo
# ---------------------------------------------------------------------------
def procesar(prov, monitor, recepcion_hist, aprobadores, informe, meses,
             excluir_recepcionadas=True, moneda_extranjera_100=True,
             tolerancia_redondeo=cfg.TOLERANCIA_REDONDEO) -> Resultado:
    lineas, excluidas = seleccionar_lineas(prov, meses, recepcion_hist, excluir_recepcionadas)
    lineas = enlazar_monitor(lineas, monitor, recepcion_hist)

    if recepcion_hist is not None and not recepcion_hist.empty:
        soc = recepcion_hist.set_index(["solped", "pos"])["sociedad_hist"].to_dict()
        lineas["sociedad_hist"] = [soc.get(k, "") for k in zip(lineas["solped"], lineas["pos"])]
    else:
        lineas["sociedad_hist"] = ""

    L, I, homol = cruzar_informe_real(
        lineas, informe, aprobadores,
        recepcionar_moneda_extranjera_100=moneda_extranjera_100,
        tolerancia_redondeo=tolerancia_redondeo,
    )

    # Responsable de recepción (bloque de la pestaña Aprobadores)
    L["responsable"] = asignar_responsable(L, aprobadores)

    return _armar_resultado(L, excluidas, I, homol, informe)


def _armar_resultado(L, excluidas, I, homol, informe) -> Resultado:
    L = L.copy()
    L["desviacion_pct"] = np.where(
        L["monto_real"].notna() & L["valor_prov"].ne(0),
        (L["monto_real"] / L["valor_prov"] - 1) * 100, np.nan,
    )
    L["observacion"] = _observaciones(L)
    L = L.sort_values(["solped", "pos"]).reset_index(drop=True)

    recepcion = armar_recepcion(L)
    gral = armar_gral(L)
    por_resp = separar_por_responsable(gral)
    sin_uso = I[~I["usada"]].copy()

    con_real = L["monto_real"].notna()
    resumen = {
        "lineas_mes": int(len(L) + len(excluidas)),
        "lineas_generadas": int(len(L)),
        "excluidas": int(len(excluidas)),
        "cruzadas": int(L["estado_cruce"].str.startswith("Cruzado").sum()),
        "revisar": int(L["estado_cruce"].str.contains("revisar").sum()),
        "ajuste_manual": int((L["estado_cruce"] == "Ajuste manual").sum()),
        "moneda_extranjera": int(L["estado_cruce"].str.startswith("Moneda").sum()),
        "sin_cruce": int((L["estado_cruce"] == "Sin cruce").sum()),
        "monto_provisorio_clp": float(L.loc[L["moneda"] == "CLP", "valor_prov"].sum()),
        "monto_real_clp": float(L.loc[(L["moneda"] == "CLP") & con_real, "monto_real"].sum()),
        "monto_informe_total": float(informe["monto_real"].sum()),
        "monto_informe_sin_uso": float(sin_uso["monto_real"].sum()),
        "filas_informe_sin_uso": int(len(sin_uso)),
    }
    res = Resultado(
        recepcion=recepcion, gral=gral, gral_por_responsable=por_resp, lineas=L,
        excluidas=excluidas, informe_sin_uso=sin_uso, homologacion=homol, resumen=resumen,
        informe_anotado=I, informe_total=informe,
    )
    return res


def aplicar_ajustes(res: Resultado, ajustes: dict) -> Resultado:
    """
    Aplica montos reales ingresados a mano desde la app
    {(solped, pos): monto} y recalcula Q, R y GRAL.
    """
    if not ajustes:
        return res
    L = res.lineas.copy()
    for (solped, pos), monto in ajustes.items():
        m = (L["solped"] == solped) & (L["pos"] == pos)
        if not m.any():
            continue
        if monto is None or (isinstance(monto, float) and np.isnan(monto)):
            L.loc[m, "monto_real"] = np.nan
            L.loc[m, "estado_cruce"] = "Sin cruce"
        else:
            L.loc[m, "monto_real"] = float(monto)
            L.loc[m, "estado_cruce"] = "Ajuste manual"
    return _armar_resultado(L, res.excluidas, res.informe_anotado, res.homologacion, res.informe_total)
