"""
Parámetros y catálogos del sistema de generación de recepciones reales.

Todo lo que el equipo pueda necesitar ajustar mes a mes (homologaciones de
marca, códigos de medio, tolerancias, constantes SAP) vive en este archivo,
de modo que la lógica de los demás módulos no tenga valores "mágicos".
"""

# ---------------------------------------------------------------------------
# Nombres de pestañas esperadas (se buscan sin distinguir mayúsculas,
# acentos ni espacios sobrantes, porque en el archivo vienen con espacios
# al final, p. ej. "Aprobadores ").
# ---------------------------------------------------------------------------
HOJA_PROVISORIOS = "PROVISORIOS"
HOJA_MONITOR_PROV = "Monitor Prov"
HOJA_RECEPCION_PROV = "Recepción PROVISORIOS"
HOJA_APROBADORES = "Aprobadores"

# Informe Real: hoja mensual ("REAL JULIO 2026") o base acumulada ("BASES 2026")
PREFIJO_HOJA_REAL = "REAL "
HOJA_BASES_REAL = "BASES"

# ---------------------------------------------------------------------------
# Meses
# ---------------------------------------------------------------------------
MESES = {
    1: ("ENE", "ENERO", "ene"),
    2: ("FEB", "FEBRERO", "feb"),
    3: ("MAR", "MARZO", "mar"),
    4: ("ABR", "ABRIL", "abr"),
    5: ("MAY", "MAYO", "may"),
    6: ("JUN", "JUNIO", "jun"),
    7: ("JUL", "JULIO", "jul"),
    8: ("AGO", "AGOSTO", "ago"),
    9: ("SEP", "SEPTIEMBRE", "sep"),
    10: ("OCT", "OCTUBRE", "oct"),
    11: ("NOV", "NOVIEMBRE", "nov"),
    12: ("DIC", "DICIEMBRE", "dic"),
}

# ---------------------------------------------------------------------------
# Estructura de salida: hoja "Recepción PROVISORIOS"
# (se replican las 29 columnas A:AC en el mismo orden que la pestaña actual)
# ---------------------------------------------------------------------------
COLUMNAS_RECEPCION = [
    "Sociedad",                    # A  crítica
    "Texto breve",                 # B  crítica
    "Proveedor fijo",              # C
    "Nombre de proveedor",         # D  crítica
    "Solicitud de pedido",         # E  crítica
    "Posición de pedido",          # F
    "Fecha de pedido",             # G  crítica
    "Pedido",                      # H  crítica
    "Hoja de entrada",             # I  (SAP)
    "Valor total",                 # J  crítica - monto provisorio
    "Moneda",                      # K  crítica
    "Documento material",          # L  (SAP)
    "Cuenta de mayor",             # M
    "Servicio",                    # N
    "Importe Contab. HES",         # O  monto real (cruce con Informe Real)
    "Moneda HES",                  # P
    "Porcentaje de Cumplimiento",  # Q  crítica
    "Desviacion por Posicion",     # R  crítica
    "Elemento PEP",                # S  crítica
    "Factura",                     # T  (SAP)
    "Fecha Factura",               # U  (SAP)
    "Fecha Contab. Factura",       # V  (SAP)
    "Fecha Pago",                  # W  (SAP)
    "Doc. Pago",                   # X  (SAP)
    "Estado Factura",              # Y  (SAP)
    "Estado Pago",                 # Z  (SAP)
    "Status tratamiento",          # AA
    "",                            # AB (columna vacía en la plantilla)
    "SOX",                         # AC
]

# Columnas que SAP completa después de subir la recepción: se dejan vacías.
COLUMNAS_SOLO_SAP = [
    "Hoja de entrada", "Documento material", "Factura", "Fecha Factura",
    "Fecha Contab. Factura", "Fecha Pago", "Doc. Pago", "Estado Factura",
    "Estado Pago",
]

COLUMNAS_CRITICAS = [
    "Sociedad", "Texto breve", "Nombre de proveedor", "Solicitud de pedido",
    "Fecha de pedido", "Pedido", "Valor total", "Moneda",
    "Porcentaje de Cumplimiento", "Desviacion por Posicion", "Elemento PEP",
]

# Colores de encabezado de la plantilla original (se replican al exportar)
COLOR_ENCABEZADO = {
    "Sociedad": "FFFF00",
    "Pedido": "FFFF00",
    "Valor total": "FFFF00",
    "Porcentaje de Cumplimiento": "FFFF00",
    "Desviacion por Posicion": "FFFF00",
    "Documento material": "4A86E8",
    "Importe Contab. HES": "FF0000",
}

# Constantes que en el histórico son idénticas en el 100 % de las filas
CUENTA_MAYOR_DEFAULT = 6000012006
SERVICIO_DEFAULT = 3000161
STATUS_TRATAMIENTO_DEFAULT = "B"

# ---------------------------------------------------------------------------
# Estructura de salida: "GRAL Recepción"
# ---------------------------------------------------------------------------
COLUMNAS_GRAL = [
    "Documento compras", "Posición", "Texto breve", "Por entregar (valor)",
    "Nombre de proveedor", "Centro", "Importe a Liberar",
    "Cantidad a Liberar", "Porcentaje a Liberar",
]
LARGO_NOMBRE_PROVEEDOR_GRAL = 24      # SAP trunca la razón social a 24 caracteres
SEPARADOR_PROVEEDOR_GRAL = "    "     # código + 4 espacios + razón social

# Pestaña por responsable en GRAL (etiqueta en columna H de "Aprobadores")
PESTANAS_RESPONSABLE = {
    "YUGLEY": "yu",
    "ELOISA": "ELO",
    "RODRIGO": "RODRI",
    "CONSTANZA": "CONI",
}

# ---------------------------------------------------------------------------
# Medios
# ---------------------------------------------------------------------------
# Grupo de medio a partir del último segmento del Elemento PEP.
# Los códigos ambiguos (111361 multimarca, 21412, etc.) se resuelven por texto.
MEDIO_POR_CODIGO_PEP = {
    "11131": "TELEVISION AIRE",
    "111301": "TELEVISION AIRE",
    "11136": "TELEVISION CABLE",
    "111306": "TELEVISION CABLE",
    "11934": "RADIO",
    "11933": "GRAFICA",
    "11230": "DIGITAL",
    "11236": "DIGITAL",
    "11237": "DIGITAL",
    "111413": "VIA PUBLICA",
    "111431": "VIA PUBLICA",
}

# Reglas de texto (se evalúan en orden; gana la primera que aparece)
MEDIO_POR_TEXTO = [
    (r"\bTELEVISION (POR )?CABLE\b|\bCABLE DE TELEVISION\b|\bTELEVISION CABLE\b|\bTVP\b|\bTVC\b", "TELEVISION CABLE"),
    (r"\bTELEVISION AIRE\b|\bTVA\b", "TELEVISION AIRE"),
    (r"\bVIA PUBLICA\b|\bVP\b", "VIA PUBLICA"),
    (r"\bGRAFICA\b|\bGRAFIC\b|\bREVISTA\b|\bPRENSA\b", "GRAFICA"),
    (r"\bDIGITAL\b|\bDIGITA\b|\bDIGIT\b|\bDIGI\b|\bDG\b|\bDI\b", "DIGITAL"),
    (r"\bRADIO\b", "RADIO"),
    (r"\bOTHER\b|\bOTROS\b", "OTHER MEDIA"),
]

# ---------------------------------------------------------------------------
# Marcas: homologación Pinta (Informe Real) -> código de marca del PEP.
# La mayoría se resuelve sola contra la pestaña "Aprobadores"; aquí van solo
# los casos cuyo nombre no coincide. Agregar nuevas equivalencias aquí.
# ---------------------------------------------------------------------------
ALIAS_MARCA_A_CODIGO = {
    "7UP": "GSEVE",
    "SEVEN UP": "GSEVE",
    "GATORLIT": "FGLIT",
    "H2OH": "GH2OH",
    "H2OH!": "GH2OH",
    "MULTIMARCAS ZERO / LIGHT": "GOTRO",
    "MULTIMARCAS ZERO LIGHT": "GOTRO",
    "TICO": "GOTRO",
    "TRES ERRES": "PTRES",
    "AGUAS MANANTIAL": "AMANA",
    "CANADA DRY GINGER ALE": "GCDGI",
    "LIPTON ICE TEA": "FLIPT",
    "ROYAL GUARD": "CROYA",
    "CRISTAL LAGER": "CCRIS",
    "CERVEZA ESCUDO": "CESCU",
    "CERVEZA SOL": "CSOL_",
    "COORS ORIGINAL": "CCOOR",
    "LEMON STONES": "CSTON",
    "TRADE MKT": "CMORE",
    "VINA MAR": "EVIÑA",
}

# Códigos de marca equivalentes (el PEP del año anterior sigue vigente en
# algunas líneas, p. ej. M.25.A90.GCDGI). La comparación se hace solo por el
# código de 5 caracteres, sin el prefijo de año, así que no requiere ajuste.

# ---------------------------------------------------------------------------
# Cruce con Informe Real
# ---------------------------------------------------------------------------
# Peso de cada componente en el puntaje de emparejamiento (0-100)
PESO_TEXTO = 0.60
PESO_MONTO = 0.40
# Puntaje mínimo para aceptar un emparejamiento automático
PUNTAJE_MINIMO = 55
# Bajo este puntaje (pero sobre el mínimo) el cruce se marca "Revisar"
PUNTAJE_REVISAR = 70
# Diferencia relativa real vs. provisorio a partir de la cual se alerta
ALERTA_DESVIACION_PCT = 20.0
# Tolerancia para considerar dos montos iguales (pesos)
TOLERANCIA_PESOS = 1

# Si |real - provisorio| <= este valor se recepciona al 100 % (el histórico
# muestra que los analistas no ajustan diferencias de redondeo de pocos pesos)
TOLERANCIA_REDONDEO = 10
# Filas del Informe Real con monto 0 (bonificadas) no se usan para el cruce
EXCLUIR_MONTO_CERO = True

# Moneda en que viene el Informe Real; líneas en otra moneda no se cruzan
MONEDA_INFORME = "CLP"

# Palabras que no aportan para distinguir vehículos
STOPWORDS_VEHICULO = {
    "DE", "DEL", "LA", "EL", "LOS", "Y", "EN", "A", "SPA", "S", "SA", "LTDA",
    "LIMITADA", "CHILE", "DIRECTO", "INDIRECTO", "ORION", "CAPITAL", "OR",
    "TELEVISION", "AIRE", "CABLE", "POR", "RADIO", "DIGITAL", "VIA",
    "PUBLICA", "VP", "TVA", "TVP", "DG", "GRAFICA",
}

# Equivalencias de palabras: el texto de carga a veces viene traducido
# ("VIDEO PROGRAMÁTICO YOUTUBE" vs. "PROGRAMMATIC VIDEO YOUTUBE")
SINONIMOS_VEHICULO = {
    "PROGRAMATICO": "PROGRAMMATIC", "PROGRAMATICA": "PROGRAMMATIC",
    "PROGRAMATIC": "PROGRAMMATIC", "PROGRAMATICOS": "PROGRAMMATIC",
    "CONECTADA": "CONNECTED", "CONECTADO": "CONNECTED",
    "TELEVISION": "TV", "VIDEOS": "VIDEO", "VD": "VIDEO", "VDYT": "VIDEO YOUTUBE",
    "YT": "YOUTUBE", "PRG": "PROGRAMMATIC", "PROGR": "PROGRAMMATIC",
    "PROGRAM": "PROGRAMMATIC", "PGR": "PROGRAMMATIC", "PG": "PROGRAMMATIC",
    "MH": "MASTHEAD", "FACEBO": "FACEBOOK", "FACE": "FACEBOOK", "META": "FACEBOOK",
    "MATT": "MATTERKIND", "PUBLICIDAD": "", "PUBLICITARIA": "",
}

# Comentarios (columna "RECEPCIÓN / COMENTARIO" de PROVISORIOS) que indican
# que la línea fue eliminada y no debe recepcionarse
PATRON_ELIMINADA = r"^\s*ELIM"
