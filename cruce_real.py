"""
Cruce de las líneas provisorias con el Informe Real de Inversión.

Cada línea provisoria (Solped + posición) se busca en el Informe Real del mes
dentro del mismo grupo  (código de marca, medio):

  * Marca: del Elemento PEP de la línea (M.26.A90.FGATO.11131 -> FGATO). En
    el Informe Real se obtiene homologando la "Pinta" contra la pestaña
    Aprobadores + ALIAS_MARCA_A_CODIGO (config) + votación con los textos de
    carga del mismo mes.
  * Medio: del código final del PEP (11131 = TV aire, ...); si el código es
    ambiguo, del texto de la línea ("Televisión aire", "TVA", "DG", "VP"...).

Dentro del grupo se arma una matriz de puntajes (similitud de vehículo y
cercanía de monto) y se resuelve un emparejamiento uno a uno. El monto real
("Monto Neto Real") de la fila emparejada pasa a la columna O.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

import config as cfg
from utils import (
    codigo_marca_pep, codigo_medio_pep, normalizar, similitud, tokens_utiles,
)

_PATRONES_MEDIO = [(re.compile(p), g) for p, g in cfg.MEDIO_POR_TEXTO]
_PALABRAS_MES = {normalizar(x) for v in cfg.MESES.values() for x in v} | {"HACE"}


# ---------------------------------------------------------------------------
# Clasificación de medio
# ---------------------------------------------------------------------------
def medio_desde_texto(*textos: str) -> str:
    """Devuelve el medio cuya palabra clave aparece primero en el texto."""
    for t in textos:
        t = normalizar(t)
        mejor, pos_min = "", None
        for patron, grupo in _PATRONES_MEDIO:
            m = patron.search(t)
            if m and (pos_min is None or m.start() < pos_min):
                mejor, pos_min = grupo, m.start()
        if mejor:
            return mejor
    return ""


def medio_linea(pep: str, texto_largo: str, texto_breve: str) -> str:
    g = cfg.MEDIO_POR_CODIGO_PEP.get(codigo_medio_pep(pep), "")
    return g or medio_desde_texto(texto_largo, texto_breve[4:] if texto_breve else "")


def medio_informe(medio: str) -> str:
    m = normalizar(medio)
    for grupo in ("TELEVISION CABLE", "TELEVISION AIRE", "VIA PUBLICA", "DIGITAL", "RADIO", "GRAFICA"):
        if grupo in m:
            return grupo
    return "OTHER MEDIA" if m else ""


# ---------------------------------------------------------------------------
# Homologación de marca (Pinta -> código PEP)
# ---------------------------------------------------------------------------
def construir_homologacion_marcas(pintas: list[str], aprobadores: pd.DataFrame,
                                  lineas: pd.DataFrame) -> pd.DataFrame:
    """
    Resuelve el código de marca de cada Pinta del Informe Real. Orden:
      1. coincidencia exacta con MARCA de Aprobadores
      2. ALIAS_MARCA_A_CODIGO de config
      3. MARCA de Aprobadores contenida en la Pinta (la más larga gana:
         'MISTRAL ICE' antes que 'MISTRAL')
      4. votación: la Pinta aparece al inicio de los textos de carga de las
         líneas del mes, y se toma el código PEP más frecuente
    """
    catalogo = {}
    if aprobadores is not None and not aprobadores.empty:
        for m, c in zip(aprobadores["marca_norm"], aprobadores["codigo_marca"]):
            catalogo.setdefault(m, c)
    alias = {normalizar(k): v for k, v in cfg.ALIAS_MARCA_A_CODIGO.items()}

    # Textos de carga por código (para votación)
    votos_textos = defaultdict(list)
    for pep, tl, tb in zip(lineas["pep"], lineas["texto_largo"], lineas["texto_breve"]):
        cod = codigo_marca_pep(pep)
        if cod:
            votos_textos[cod].append(normalizar(tl))
            votos_textos[cod].append(normalizar(tb[4:] if tb else ""))

    codigos_con_lineas = {codigo_marca_pep(p) for p in lineas["pep"]} - {""}
    codigos_con_lineas |= set(lineas.get("codigo_marca_texto", pd.Series(dtype=str))) - {""}

    filas = []
    for p in sorted(set(pintas)):
        n = normalizar(p)
        cod, regla = catalogo.get(n), "Aprobadores (exacta)"
        if not cod and n in alias:
            cod, regla = alias[n], "Alias config"
        if not cod:
            cands = [(len(m), c) for m, c in catalogo.items()
                     if m and re.search(rf"\b{re.escape(m)}\b", n)]
            if cands:
                cod, regla = max(cands)[1], "Aprobadores (contenida)"
            # Si la marca contenida no tiene líneas en el mes, pero otra marca
            # que comparte la primera palabra sí (CAMPANARIO COCTEL -> la línea
            # viene como CAMPANARIO SOUR), se usa esa.
            primera = n.split()[0] if n else ""
            if (not cod or cod not in codigos_con_lineas) and primera:
                hermanas = {c for m, c in catalogo.items()
                            if m.split()[:1] == [primera] and c in codigos_con_lineas}
                if len(hermanas) == 1:
                    cod, regla = hermanas.pop(), "Aprobadores (misma primera palabra, con líneas en el mes)"
        if not cod:
            conteo = Counter()
            for c, textos in votos_textos.items():
                conteo[c] = sum(1 for t in textos if t.startswith(n + " ") or t == n)
            if conteo and conteo.most_common(1)[0][1] > 0:
                cod, regla = conteo.most_common(1)[0][0], "Votación textos de carga"
        filas.append({"pinta": p, "pinta_norm": n, "codigo_marca": cod or "",
                      "regla": regla if cod else "Sin homologar"})
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# Similitud de vehículo
# ---------------------------------------------------------------------------
def _quitar_ruido(texto: str, marca_tokens: set[str]) -> str:
    """Normaliza, quita marca, mes y dígitos sueltos ('-6') y aplica sinónimos."""
    toks = []
    for t in normalizar(texto).split():
        if t in _PALABRAS_MES or t in marca_tokens or re.fullmatch(r"\d", t):
            continue
        t = cfg.SINONIMOS_VEHICULO.get(t, t)
        if t:
            toks.extend(t.split())
    return " ".join(toks)


def _cobertura(tok_inf: set[str], tok_lin: set[str]) -> float:
    """Fracción de palabras del vehículo (informe) presentes en la línea,
    aceptando truncados SAP ('PROGR' ~ 'PROGRAMMATIC')."""
    if not tok_inf:
        return 0.0
    hit = 0
    for a in tok_inf:
        for b in tok_lin:
            if a == b or (min(len(a), len(b)) >= 3 and (a.startswith(b) or b.startswith(a))):
                hit += 1
                break
    return hit / len(tok_inf)


def _tokens_con_numero(tokens: set[str]) -> set[str]:
    return {t for t in tokens if re.search(r"\d", t)}


def puntaje_vehiculo(veh_inf: str, razon_inf: str, textos_linea: list[str]) -> float:
    tok_inf = tokens_utiles(veh_inf, cfg.STOPWORDS_VEHICULO)
    tok_lin = set()
    for t in textos_linea:
        tok_lin |= tokens_utiles(t, cfg.STOPWORDS_VEHICULO)
    fuzzy = max((similitud(veh_inf, t) for t in textos_linea if t), default=0.0)
    cobertura = 100 * _cobertura(tok_inf, tok_lin) if tok_inf else fuzzy
    s = 0.5 * fuzzy + 0.5 * cobertura
    # Canales/frecuencias (C11 vs C13, T13 VIVO, MEGA 2...): si ambos lados
    # traen un identificador con número y no coinciden, se castiga fuerte.
    num_inf, num_lin = _tokens_con_numero(tok_inf), _tokens_con_numero(tok_lin)
    if num_inf and num_lin and not (num_inf & num_lin):
        s *= 0.35
    # Razón social del medio como apoyo cuando el vehículo es genérico
    if razon_inf:
        s = max(s, 0.8 * max((similitud(normalizar(razon_inf), t) for t in textos_linea if t), default=0.0))
    return s


def puntaje_monto(real: float, prov: float) -> float:
    if real is None or prov is None or (isinstance(prov, float) and math.isnan(prov)):
        return 0.0
    if abs(real - prov) <= cfg.TOLERANCIA_PESOS:
        return 100.0
    rel = abs(real - prov) / max(abs(prov), 1.0)
    return 100.0 * math.exp(-3.0 * rel)


# ---------------------------------------------------------------------------
# Marca declarada en el texto de la línea
# ---------------------------------------------------------------------------
def marca_desde_texto(texto_largo: str, texto_breve: str, aprobadores: pd.DataFrame) -> str:
    """
    Código de marca según el nombre con que parte el texto de carga
    ('TICO Vía pública T & S Jul -6' -> GOTRO). Sirve cuando la línea se
    imputó al PEP de otra marca (caso TICO con PEP de Bilz & Pap / 7UP).
    """
    nombres = {}
    if aprobadores is not None and not aprobadores.empty:
        nombres.update(dict(zip(aprobadores["marca_norm"], aprobadores["codigo_marca"])))
    nombres.update({normalizar(k): v for k, v in cfg.ALIAS_MARCA_A_CODIGO.items()})
    for t in (normalizar(texto_largo), normalizar(texto_breve[4:] if texto_breve else "")):
        mejor = ""
        largo = 0
        for nom, cod in nombres.items():
            if nom and (t == nom or t.startswith(nom + " ")) and len(nom) > largo:
                mejor, largo = cod, len(nom)
        if mejor:
            return mejor
    return ""


# ---------------------------------------------------------------------------
# Cruce
# ---------------------------------------------------------------------------
def cruzar_informe_real(lineas: pd.DataFrame, informe: pd.DataFrame,
                        aprobadores: pd.DataFrame,
                        recepcionar_moneda_extranjera_100: bool = True,
                        tolerancia_redondeo: float = cfg.TOLERANCIA_REDONDEO):
    """
    Devuelve (lineas_cruzadas, informe_anotado, homologacion_marcas).

    lineas_cruzadas agrega: monto_real, estado_cruce, puntaje_cruce,
    fila_informe y las columnas del Informe Real con encabezado amarillo
    (Pinta, ID Medio, Medio, Proveedor-Vehiculo, Burst) más Tipo.
    """
    L = lineas.copy()
    I = informe.copy()

    L["codigo_marca"] = L["pep"].map(codigo_marca_pep)
    L["codigo_marca_texto"] = [marca_desde_texto(tl, tb, aprobadores)
                               for tl, tb in zip(L["texto_largo"], L["texto_breve"])]
    L["medio_grupo"] = [medio_linea(p, tl, tb) for p, tl, tb in zip(L["pep"], L["texto_largo"], L["texto_breve"])]

    homol = construir_homologacion_marcas(I["pinta"].tolist(), aprobadores, L)
    mapa_cod = dict(zip(homol["pinta"], homol["codigo_marca"]))
    I["codigo_marca"] = I["pinta"].map(mapa_cod).fillna("")
    I["medio_grupo"] = I["medio"].map(medio_informe)
    I["usada"] = False
    I["linea_asignada"] = ""
    I["motivo_no_uso"] = ""
    if cfg.EXCLUIR_MONTO_CERO:
        cero = I["monto_real"].abs() < 0.5
        I.loc[cero, "motivo_no_uso"] = "Monto real 0 (bonificada)"

    for c in ["monto_real", "monto_informe", "puntaje_cruce", "fila_informe"]:
        L[c] = np.nan
    for c in ["estado_cruce", "paso_cruce", "inf_pinta", "inf_id_medio", "inf_medio",
              "inf_vehiculo", "inf_burst", "inf_tipo"]:
        L[c] = ""

    # Tokens de marca a ignorar al comparar vehículos
    marca_tokens = defaultdict(set)
    for p, cod in mapa_cod.items():
        if cod:
            marca_tokens[cod] |= set(normalizar(p).split())
    if aprobadores is not None and not aprobadores.empty:
        for m, cod in zip(aprobadores["marca_norm"], aprobadores["codigo_marca"]):
            marca_tokens[cod] |= set(m.split())

    # Líneas en moneda distinta a la del informe: no se cruzan
    extranjera = L["moneda"].ne(cfg.MONEDA_INFORME)
    if recepcionar_moneda_extranjera_100:
        L.loc[extranjera, "monto_real"] = L.loc[extranjera, "valor_prov"]
        L.loc[extranjera, "estado_cruce"] = "Moneda extranjera: 100 %"
    else:
        L.loc[extranjera, "estado_cruce"] = "Moneda extranjera: sin cruce"
    candidatas = list(L.index[~extranjera])

    def _asignar(idx_l, idx_i, puntaje, etiqueta, paso):
        fila = I.loc[idx_i]
        real = fila["monto_real"]
        L.at[idx_l, "monto_informe"] = real
        if abs(real - L.at[idx_l, "valor_prov"]) <= tolerancia_redondeo:
            # Diferencia de redondeo: se respeta el provisorio (100 %)
            L.at[idx_l, "monto_real"] = L.at[idx_l, "valor_prov"]
            if abs(real - L.at[idx_l, "valor_prov"]) > cfg.TOLERANCIA_PESOS:
                etiqueta += " (dif. redondeo)"
        else:
            L.at[idx_l, "monto_real"] = real
        L.at[idx_l, "puntaje_cruce"] = round(puntaje, 1)
        L.at[idx_l, "fila_informe"] = fila["fila_informe"]
        L.at[idx_l, "inf_pinta"] = fila["pinta"]
        L.at[idx_l, "inf_id_medio"] = fila["id_medio"]
        L.at[idx_l, "inf_medio"] = fila["medio"]
        L.at[idx_l, "inf_vehiculo"] = fila["vehiculo"]
        L.at[idx_l, "inf_burst"] = fila["burst"]
        L.at[idx_l, "inf_tipo"] = fila["tipo"]
        L.at[idx_l, "estado_cruce"] = etiqueta
        L.at[idx_l, "paso_cruce"] = f"Paso {paso}"
        I.at[idx_i, "usada"] = True
        I.at[idx_i, "linea_asignada"] = f"{L.at[idx_l, 'solped']}/{L.at[idx_l, 'pos']}"

    def _textos_linea(idx, cod):
        mt = marca_tokens.get(cod, set()) | marca_tokens.get(L.at[idx, "codigo_marca_texto"], set())
        return [_quitar_ruido(L.at[idx, "texto_largo"], mt),
                _quitar_ruido(L.at[idx, "texto_breve"][4:], mt)]

    def _libres(idx):
        return [j for j in idx if not I.at[j, "usada"] and I.at[j, "motivo_no_uso"] == ""]

    def _resolver(idx_lineas, idx_informe, paso, factor=1.0, exigir_marca_texto=False,
                  aceptar_monto_exacto=False):
        idx_lineas = [i for i in idx_lineas if L.at[i, "estado_cruce"] == ""]
        idx_informe = _libres(idx_informe)
        if not idx_lineas or not idx_informe:
            return
        S = np.zeros((len(idx_lineas), len(idx_informe)))
        SM = np.zeros_like(S)
        for a, il in enumerate(idx_lineas):
            cod = L.at[il, "codigo_marca"]
            tl = _textos_linea(il, cod)
            for b, ii in enumerate(idx_informe):
                fila = I.loc[ii]
                veh = _quitar_ruido(fila["vehiculo"], marca_tokens.get(fila["codigo_marca"], set()))
                sv = puntaje_vehiculo(veh, fila["razon_social"], tl)
                sm = puntaje_monto(fila["monto_real"], L.at[il, "valor_prov"])
                sc = cfg.PESO_TEXTO * sv + cfg.PESO_MONTO * sm
                if exigir_marca_texto:
                    sb = similitud(normalizar(fila["pinta"]),
                                   normalizar(L.at[il, "texto_largo"] or L.at[il, "texto_breve"][4:]))
                    sc *= 0.5 + 0.5 * sb / 100
                S[a, b] = sc * factor
                SM[a, b] = sm
        fi, co = linear_sum_assignment(-S)
        for a, b in zip(fi, co):
            sc = S[a, b]
            if sc >= cfg.PUNTAJE_MINIMO:
                etiqueta = "Cruzado" if (sc >= cfg.PUNTAJE_REVISAR and paso == 1) else "Cruzado - revisar"
                _asignar(idx_lineas[a], idx_informe[b], sc, etiqueta, paso)
            elif aceptar_monto_exacto and SM[a, b] >= 100:
                _asignar(idx_lineas[a], idx_informe[b], sc, "Cruzado - revisar", paso)

    grupos_inf = I.groupby(["codigo_marca", "medio_grupo"]).groups
    grupos_marca = I.groupby("codigo_marca").groups

    # Paso 1: mismo código de marca (PEP) y mismo medio
    for (cod, med), idx_l in L.loc[candidatas].groupby(["codigo_marca", "medio_grupo"]).groups.items():
        idx_i = grupos_inf.get((cod, med))
        if cod and idx_i is not None:
            _resolver(list(idx_l), list(idx_i), paso=1)

    # Paso 2: marca según el texto de la línea (cuando difiere del PEP), mismo medio
    pend = [i for i in candidatas if L.at[i, "estado_cruce"] == ""]
    por_texto = defaultdict(list)
    for i in pend:
        ct = L.at[i, "codigo_marca_texto"]
        if ct and ct != L.at[i, "codigo_marca"]:
            por_texto[(ct, L.at[i, "medio_grupo"])].append(i)
    for (cod, med), idx_l in por_texto.items():
        idx_i = grupos_inf.get((cod, med))
        if idx_i is not None:
            _resolver(idx_l, list(idx_i), paso=2)

    # Paso 3: misma marca (PEP o texto) en otro medio (p. ej. 'Other' en SAP
    # que el informe clasifica distinto). Se acepta con monto exacto.
    pend = [i for i in candidatas if L.at[i, "estado_cruce"] == ""]
    por_marca = defaultdict(list)
    for i in pend:
        for cod in {L.at[i, "codigo_marca"], L.at[i, "codigo_marca_texto"]} - {""}:
            por_marca[cod].append(i)
    for cod, idx_l in por_marca.items():
        idx_i = grupos_marca.get(cod)
        if idx_i is not None:
            _resolver(idx_l, list(idx_i), paso=3, factor=0.9, aceptar_monto_exacto=True)

    # Paso 4: filas del informe sin marca homologada, mismo medio; el nombre
    # de la Pinta debe parecerse al texto de la línea.
    pend = [i for i in candidatas if L.at[i, "estado_cruce"] == ""]
    sin_marca = [j for j in I.index if I.at[j, "codigo_marca"] == ""]
    for med in {L.at[i, "medio_grupo"] for i in pend}:
        idx_l = [i for i in pend if L.at[i, "medio_grupo"] == med]
        idx_i = [j for j in sin_marca if I.at[j, "medio_grupo"] == med]
        _resolver(idx_l, idx_i, paso=4, exigir_marca_texto=True)

    L.loc[L["estado_cruce"] == "", "estado_cruce"] = "Sin cruce"
    I.loc[~I["usada"] & (I["motivo_no_uso"] == ""), "motivo_no_uso"] = "Sin línea provisoria asociada"

    L["desviacion_pct"] = np.where(
        L["monto_real"].notna() & L["valor_prov"].ne(0),
        (L["monto_real"] / L["valor_prov"] - 1) * 100, np.nan,
    )
    return L, I, homol
