"""
Enlace PROVISORIOS <-> Monitor Prov.

PROVISORIOS (extracción SAP) trae Solped, posición, Pedido y montos, pero no
el Elemento PEP ni el texto largo de la carga. Esos datos están en Monitor Prov
(archivo de carga), donde "NRO DOC" = Solped. Como el número de LINEA del
monitor no es la posición SAP (10, 20, 30...), cada posición se empareja con
su línea de carga dentro de la misma Solped usando:

  1. igualdad de monto (criterio principal),
  2. similitud entre el texto breve SAP y el texto de la carga,
  3. orden relativo (posición SAP vs. LINEA del monitor) como desempate.

El emparejamiento es uno a uno (algoritmo húngaro por Solped).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

import config as cfg
from utils import normalizar, similitud


UMBRAL_TEXTO_SIN_MONTO = 75


def _texto_sin_prefijo_mes(t: str) -> str:
    return normalizar(t[4:] if len(t) > 4 and t[0] == "M" else t)


def enlazar_monitor(prov: pd.DataFrame, monitor: pd.DataFrame,
                    recepcion_hist: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Agrega a `prov` las columnas del monitor: pep, texto_largo, servicio,
    rut_proveedor, sox, ref_externa, y 'origen_pep' que indica de dónde se
    obtuvo el PEP (Monitor Prov / Recepción histórica / sin dato).
    """
    prov = prov.copy()
    for c in ["pep", "texto_largo", "rut_proveedor", "sox", "ref_externa"]:
        prov[c] = ""
    prov["servicio"] = np.nan
    prov["fila_monitor"] = np.nan
    prov["origen_pep"] = "Sin dato"
    prov["puntaje_enlace"] = np.nan

    mon_por_doc = {k: g for k, g in monitor.groupby("nro_doc")}

    for solped, grupo in prov.groupby("solped"):
        cand = mon_por_doc.get(solped)
        if cand is None or cand.empty:
            continue
        P = grupo.sort_values("pos")
        M = cand.sort_values("linea")
        n_p, n_m = len(P), len(M)
        score = np.zeros((n_p, n_m))
        sim = np.zeros((n_p, n_m))
        igual_m = np.zeros((n_p, n_m), dtype=bool)
        rank_p = np.linspace(0, 1, n_p) if n_p > 1 else np.zeros(1)
        rank_m = np.linspace(0, 1, n_m) if n_m > 1 else np.zeros(1)
        textos_p = [_texto_sin_prefijo_mes(t) for t in P["texto_breve"]]
        textos_m = [normalizar(t) for t in M["texto_largo"]]
        montos_p = P["valor_prov"].to_numpy(dtype=float)
        montos_m = M["monto_monitor"].to_numpy(dtype=float)
        for i in range(n_p):
            for j in range(n_m):
                igual = (
                    not np.isnan(montos_p[i]) and not np.isnan(montos_m[j])
                    and abs(montos_p[i] - montos_m[j]) <= cfg.TOLERANCIA_PESOS
                )
                sim[i, j] = similitud(textos_p[i], textos_m[j])
                igual_m[i, j] = igual
                score[i, j] = (
                    (100 if igual else 0)
                    + 0.5 * sim[i, j]
                    + 10 * (1 - abs(rank_p[i] - rank_m[j]))
                )
        filas, cols = linear_sum_assignment(-score)
        for i, j in zip(filas, cols):
            s = score[i, j]
            # Aceptar si coincide el monto o, sin monto, si el texto es muy similar
            if not igual_m[i, j] and sim[i, j] < UMBRAL_TEXTO_SIN_MONTO:
                continue
            idx = P.index[i]
            m = M.iloc[j]
            prov.at[idx, "pep"] = m["pep"]
            prov.at[idx, "texto_largo"] = m["texto_largo"]
            prov.at[idx, "servicio"] = m["servicio"]
            prov.at[idx, "rut_proveedor"] = m["rut_proveedor"]
            prov.at[idx, "sox"] = m["sox"]
            prov.at[idx, "ref_externa"] = m["ref_externa"]
            prov.at[idx, "fila_monitor"] = m["fila_monitor"]
            prov.at[idx, "origen_pep"] = "Monitor Prov" if igual_m[i, j] else "Monitor Prov (por texto)"
            prov.at[idx, "puntaje_enlace"] = round(s, 1)

    # Respaldo: si la posición ya existe en la Recepción histórica, usar su PEP
    if recepcion_hist is not None and not recepcion_hist.empty:
        hist = recepcion_hist.set_index(["solped", "pos"])["pep_hist"].to_dict()
        sin_pep = prov["pep"] == ""
        for idx in prov.index[sin_pep]:
            pep = hist.get((prov.at[idx, "solped"], prov.at[idx, "pos"]), "")
            if pep:
                prov.at[idx, "pep"] = pep
                prov.at[idx, "origen_pep"] = "Recepción histórica"
    return prov
