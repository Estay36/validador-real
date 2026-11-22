"""
Exportación a Excel con el mismo formato visual de las planillas originales.

  * Recepcion_PROVISORIOS_<MES>.xlsx  (3 hojas)
      1. "Recepción PROVISORIOS": columnas A:AC idénticas a la pestaña del
         archivo de cargas y, desde AE, la trazabilidad con el Informe Real
         (estado, observación y columnas amarillas del informe).
      2. "Resumen": cifras del mes y, si existen, las líneas sin cruce que
         hay que completar a mano.
      3. "Control": líneas del mes no incluidas (y por qué) y filas del
         Informe Real que no corresponden a ninguna línea provisoria.
  * GRAL_RECEPCION_<MES>.xlsx
      - "Data" + una pestaña por responsable (yu, ELO, RODRI, CONI), igual
        que el GRAL que se usa hoy.

Formato de montos: pesos sin decimales; otras monedas (USD) con dos.
"""
from __future__ import annotations

import io

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import config as cfg

_FUENTE = "Calibri"
_BORDE = Border(bottom=Side(style="thin", color="999999"))
_AZUL = "1F4E79"
_RELLENO_SIN_CRUCE = PatternFill("solid", fgColor="F4CCCC")
_RELLENO_TRAZA = PatternFill("solid", fgColor="D9D9D9")
_RELLENO_AMARILLO = PatternFill("solid", fgColor="FFFF00")
_RELLENO_GRIS_GRAL = PatternFill("solid", fgColor="C0C0C0")
_RELLENO_TITULO_TABLA = PatternFill("solid", fgColor=_AZUL)

FMT_PESOS = "#,##0"
FMT_DIVISA = "#,##0.00"
FMT_PORCENTAJE = "0.00"
FMT_ENTERO = "0"
FMT_FECHA = "dd-mm-yyyy"

# Columnas de monto: su formato depende de la moneda de la fila
_COLS_MONTO = {
    "Valor total", "Importe Contab. HES", "Desviacion por Posicion",
    "Por entregar (valor)", "Importe a Liberar", "Cantidad a Liberar",
    "Valor provisorio", "Importe real",
}
# Columnas en pesos siempre (vienen del Informe Real)
_COLS_PESOS = {"Monto Neto Real"}
_COLS_PORCENTAJE = {"Porcentaje de Cumplimiento", "Porcentaje a Liberar"}
_COLS_ENTERO = {
    "Proveedor fijo", "Solicitud de pedido", "Posición de pedido", "Pedido",
    "Cuenta de mayor", "Servicio", "Fila Informe Real", "Posición", "Líneas", "Filas",
}
# Columnas del Informe Real con encabezado amarillo en el origen
_TRAZA_AMARILLAS = {"Pinta", "ID Medio", "Medio", "Proveedor-Vehiculo", "Burst", "Monto Neto Real"}


def _formato(columna: str, valor, moneda: str | None) -> str | None:
    if hasattr(valor, "year"):
        return FMT_FECHA
    if not isinstance(valor, (int, float)):
        return None
    if columna in _COLS_MONTO:
        return FMT_PESOS if (moneda or "CLP") == "CLP" else FMT_DIVISA
    if columna in _COLS_PESOS:
        return FMT_PESOS
    if columna in _COLS_PORCENTAJE:
        return FMT_PORCENTAJE
    if columna in _COLS_ENTERO:
        return FMT_ENTERO
    return None


def _escribir_tabla(ws, df: pd.DataFrame, fila_ini=1, col_ini=1, rellenos=None,
                    monedas=None, relleno_titulo=None, ancho_max=45, ajustar_ancho=True):
    """Escribe df con encabezado en `fila_ini`. `monedas`: lista alineada con
    las filas, para elegir el formato de los montos. Devuelve la última fila."""
    rellenos = rellenos or {}
    for j, nombre in enumerate(df.columns):
        c = ws.cell(row=fila_ini, column=col_ini + j, value=nombre if nombre else None)
        c.font = Font(name=_FUENTE, bold=True, size=10,
                      color="FFFFFF" if relleno_titulo is not None else "000000")
        c.alignment = Alignment(vertical="center", wrap_text=True)
        c.border = _BORDE
        relleno = rellenos.get(nombre, relleno_titulo)
        if relleno is not None:
            c.fill = relleno
    for i, fila in enumerate(df.itertuples(index=False), start=1):
        moneda = monedas[i - 1] if monedas is not None else None
        for j, valor in enumerate(fila):
            if isinstance(valor, float):
                if pd.isna(valor):
                    valor = None
                elif valor.is_integer():
                    valor = int(valor)          # 10443000.0 -> 10443000
            c = ws.cell(row=fila_ini + i, column=col_ini + j, value=valor)
            c.font = Font(name=_FUENTE, size=10)
            fmt = _formato(df.columns[j], valor, moneda)
            if fmt:
                c.number_format = fmt
    if ajustar_ancho:
        for j, nombre in enumerate(df.columns):
            letra = get_column_letter(col_ini + j)
            muestra = max((len(str(v)) for v in df.iloc[:200, j].tolist() if v is not None), default=0)
            ancho = min(max(len(str(nombre)), muestra, 6) + 2, ancho_max)
            ws.column_dimensions[letra].width = max(ws.column_dimensions[letra].width or 0, ancho)
    ws.row_dimensions[fila_ini].height = 30
    return fila_ini + len(df)


def _titulo(ws, fila, texto, subtitulo=None):
    ws.cell(row=fila, column=1, value=texto).font = Font(name=_FUENTE, bold=True, size=12, color=_AZUL)
    if subtitulo:
        ws.cell(row=fila + 1, column=1, value=subtitulo).font = Font(name=_FUENTE, italic=True, size=10, color="595959")
        return fila + 2
    return fila + 1


# ---------------------------------------------------------------------------
# Hoja 1: Recepción PROVISORIOS
# ---------------------------------------------------------------------------
def _hoja_recepcion(wb, recepcion: pd.DataFrame):
    ws = wb.active
    ws.title = cfg.HOJA_RECEPCION_PROV
    monedas = recepcion["Moneda"].tolist() if not recepcion.empty else []
    plantilla = recepcion[cfg.COLUMNAS_RECEPCION]
    rellenos = {k: PatternFill("solid", fgColor=v) for k, v in cfg.COLOR_ENCABEZADO.items()}
    _escribir_tabla(ws, plantilla, rellenos=rellenos, monedas=monedas)

    traza = recepcion[[c for c in recepcion.columns if c.startswith("_")]].copy()
    traza.columns = [c[1:] for c in traza.columns]
    col_traza = len(cfg.COLUMNAS_RECEPCION) + 2          # deja AD en blanco
    rell_traza = {c: (_RELLENO_AMARILLO if c in _TRAZA_AMARILLAS else _RELLENO_TRAZA) for c in traza.columns}
    _escribir_tabla(ws, traza, col_ini=col_traza, rellenos=rell_traza, monedas=monedas, ancho_max=60)
    ws.column_dimensions[get_column_letter(col_traza - 1)].width = 3

    # Línea sin cruce: columna O en rojo (hay que completarla a mano)
    col_o = cfg.COLUMNAS_RECEPCION.index("Importe Contab. HES") + 1
    for i, estado in enumerate(recepcion.get("_Estado cruce", []), start=2):
        if estado == "Sin cruce":
            ws.cell(row=i, column=col_o).fill = _RELLENO_SIN_CRUCE
    ws.freeze_panes = "C2"
    ultima_col = get_column_letter(col_traza + traza.shape[1] - 1)
    ws.auto_filter.ref = f"A1:{ultima_col}{max(len(recepcion), 1) + 1}"


# ---------------------------------------------------------------------------
# Hoja 2: Resumen
# ---------------------------------------------------------------------------
def _hoja_resumen(wb, res, contexto: dict):
    ws = wb.create_sheet("Resumen")
    r = res.resumen
    fila = _titulo(ws, 1, "Recepción real de pagos provisorios",
                   f"{contexto.get('mes_txt', '')} · Informe: {contexto.get('hoja_informe', '')} · "
                   f"Generado el {contexto.get('fecha', '')}")
    fila += 1

    bloques = [
        ("Líneas del mes", [
            ("Líneas provisorias del mes", r["lineas_mes"]),
            ("No incluidas (detalle en hoja Control)", r["excluidas"]),
            ("Incluidas en esta planilla", r["lineas_generadas"]),
            ("   Cruzadas con el Informe Real", r["cruzadas"]),
            ("   En moneda extranjera (100 % del provisorio)", r["moneda_extranjera"]),
            ("   Sin cruce: completar columna O a mano", r["sin_cruce"]),
            ("Gasto real sin provisorio (al final del GRAL, en naranjo)", r.get("filas_real_sin_provisorio", 0)),
        ]),
        ("Montos en pesos", [
            ("Provisorio de las líneas incluidas (J)", r["monto_provisorio_clp"]),
            ("Real asignado a las líneas incluidas (O)", r["monto_real_clp"]),
            ("Diferencia (O − J)", r["monto_real_clp"] - r["monto_provisorio_clp"]),
            ("Informe Real: asociado a líneas ya recepcionadas", r.get("monto_informe_ya_recepcionado", 0.0)),
            ("Informe Real: sin línea provisoria (detalle en hoja Control)", r["monto_informe_sin_uso"]),
            ("   de ello, gasto real sin provisorio incluido en el GRAL", r.get("monto_real_sin_provisorio", 0.0)),
        ]),
    ]
    for titulo, filas in bloques:
        ws.cell(row=fila, column=1, value=titulo).font = Font(name=_FUENTE, bold=True, size=11, color=_AZUL)
        fila += 1
        for k, v in filas:
            c1 = ws.cell(row=fila, column=1, value=k)
            c1.font = Font(name=_FUENTE, size=10, bold=not k.startswith(" "))
            c2 = ws.cell(row=fila, column=2, value=int(round(v)) if isinstance(v, float) else v)
            c2.font = Font(name=_FUENTE, size=10)
            c2.number_format = FMT_PESOS
            fila += 1
        fila += 1

    # Líneas sin cruce: lo único que requiere acción manual
    L = res.lineas
    sin = L[L["estado_cruce"] == "Sin cruce"]
    fila = _titulo(ws, fila, "Líneas sin cruce",
                   "No se encontró su fila en el Informe Real. Completar la columna O (Importe Contab. HES) "
                   "en la hoja Recepción PROVISORIOS y el Importe a Liberar en el GRAL.")
    if sin.empty:
        ws.cell(row=fila, column=1, value="No hay líneas sin cruce.").font = Font(name=_FUENTE, size=10)
        fila += 2
    else:
        tabla = pd.DataFrame({
            "Texto breve": sin["texto_breve"], "Solicitud de pedido": sin["solped"],
            "Posición de pedido": sin["pos"], "Pedido": sin["pedido"],
            "Valor total": sin["valor_prov"], "Pinta": sin["pinta_salida"], "Medio": sin["medio_salida"],
        })
        fila = _escribir_tabla(ws, tabla, fila_ini=fila, relleno_titulo=_RELLENO_TITULO_TABLA,
                               monedas=sin["moneda"].tolist(), ajustar_ancho=False) + 2

    # Marcas del Informe Real sin código PEP (solo si existen)
    hom = res.homologacion
    pend = hom[hom["codigo_marca"] == ""] if hom is not None and not hom.empty else pd.DataFrame()
    if not pend.empty:
        fila = _titulo(ws, fila, "Marcas del Informe Real sin homologar",
                       "No se reconoció su código PEP: agregarlas en ALIAS_MARCA_A_CODIGO (config.py).")
        for p in pend["pinta"]:
            ws.cell(row=fila, column=1, value=p.strip()).font = Font(name=_FUENTE, size=10)
            fila += 1

    for col, ancho in zip("ABCDEFG", (58, 20, 18, 14, 16, 24, 20)):
        ws.column_dimensions[col].width = ancho


# ---------------------------------------------------------------------------
# Hoja 3: Control
# ---------------------------------------------------------------------------
def _hoja_control(wb, res):
    ws = wb.create_sheet("Control")
    fila = _titulo(ws, 1, "Líneas del mes no incluidas",
                   "Líneas de PROVISORIOS del mes que no van en la planilla, y el motivo.")
    ex = res.excluidas
    if ex.empty:
        ws.cell(row=fila, column=1, value="Todas las líneas del mes están incluidas.").font = Font(name=_FUENTE, size=10)
        fila += 2
    else:
        conteo = ex["motivo_exclusion"].value_counts().rename_axis("Motivo").reset_index(name="Líneas")
        fila = _escribir_tabla(ws, conteo, fila_ini=fila, relleno_titulo=_RELLENO_TITULO_TABLA, ajustar_ancho=False) + 2
        det = pd.DataFrame({
            "Texto breve": ex["texto_breve"], "Solicitud de pedido": ex["solped"],
            "Posición de pedido": ex["pos"], "Pedido": ex["pedido_txt"],
            "Valor total": ex["valor_prov"], "Motivo": ex["motivo_exclusion"],
            "Comentario en PROVISORIOS": ex["comentario"],
        }).sort_values(["Motivo", "Solicitud de pedido", "Posición de pedido"])
        fila = _escribir_tabla(ws, det, fila_ini=fila, relleno_titulo=_RELLENO_TITULO_TABLA,
                               monedas=ex.loc[det.index, "moneda"].tolist(), ajustar_ancho=False) + 3

    fila = _titulo(ws, fila, "Filas del Informe Real sin línea provisoria",
                   "Gasto real del mes que no corresponde a ninguna línea de PROVISORIOS, pendiente ni ya "
                   "recepcionada (p. ej. Meta/Google directo en CLP, bonificadas en $0, montos sin provisorio).")
    su = res.informe_sin_uso
    if su.empty:
        ws.cell(row=fila, column=1, value="Todas las filas del Informe Real tienen línea asociada.").font = Font(name=_FUENTE, size=10)
    else:
        tabla = pd.DataFrame({
            "Pinta": su["pinta"].str.strip(), "Medio": su["medio"],
            "Proveedor-Vehiculo": su["vehiculo"], "Burst": su["burst"],
            "Monto Neto Real": su["monto_real"], "Motivo": su["motivo_no_uso"],
            "Fila Informe Real": su["fila_informe"],
        })
        _escribir_tabla(ws, tabla, fila_ini=fila, relleno_titulo=_RELLENO_TITULO_TABLA, ajustar_ancho=False)

    for col, ancho in zip("ABCDEFG", (40, 20, 34, 42, 18, 34, 40)):
        ws.column_dimensions[col].width = ancho


def exportar_recepcion(res, contexto: dict) -> bytes:
    wb = Workbook()
    _hoja_recepcion(wb, res.recepcion)
    _hoja_resumen(wb, res, contexto)
    _hoja_control(wb, res)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


_RELLENO_SIN_PROVISORIO = PatternFill("solid", fgColor="FCE5CD")


def _hoja_gral(ws, df: pd.DataFrame):
    rellenos = {c: _RELLENO_GRIS_GRAL for c in cfg.COLUMNAS_GRAL}
    mon = df["_Moneda"].tolist() if "_Moneda" in df else None
    _escribir_tabla(ws, df[cfg.COLUMNAS_GRAL], rellenos=rellenos, monedas=mon, ancho_max=60)
    estados = df["_Estado cruce"].tolist() if "_Estado cruce" in df else []
    col_imp = cfg.COLUMNAS_GRAL.index("Importe a Liberar") + 1
    for i, est in enumerate(estados, start=2):
        if est == "Real sin provisorio":       # fila completa en naranjo
            for j in range(1, len(cfg.COLUMNAS_GRAL) + 1):
                ws.cell(row=i, column=j).fill = _RELLENO_SIN_PROVISORIO
        elif est == "Sin cruce":                # importe por completar en rojo
            ws.cell(row=i, column=col_imp).fill = _RELLENO_SIN_CRUCE
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(cfg.COLUMNAS_GRAL))}{max(len(df), 1) + 1}"


def exportar_gral(res) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Data"
    _hoja_gral(ws, res.gral)
    for nombre, df in res.gral_por_responsable.items():
        _hoja_gral(wb.create_sheet(str(nombre)[:31]), df)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
