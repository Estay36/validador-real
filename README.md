# Recepción real de pagos provisorios

Módulo del *Sistema de automatización de revisión de planillas de pago*. Genera, a partir de la pestaña **PROVISORIOS** del archivo de cargas de medios y del **Informe Real de Inversión** del mes:

1. La hoja **Recepción PROVISORIOS** (columnas A:AC idénticas a la pestaña actual), con la columna O (*Importe Contab. HES*) poblada con el monto real y las columnas Q y R recalculadas.
2. El archivo **GRAL Recepción** (hoja *Data* y una pestaña por responsable: yu, ELO, RODRI, CONI).

Las columnas que SAP completa al subir la recepción (Hoja de entrada, Documento material, Factura, fechas y estados de pago) se dejan vacías.

## Archivos de entrada

| Archivo | Pestañas usadas | Para qué |
|---|---|---|
| CARGAS MEDIOS (.xlsx) | `PROVISORIOS` | Base de líneas: Solped, posición, Pedido, texto, monto provisorio, proveedor, centro |
| | `Monitor Prov` | Elemento PEP, servicio, SOX y texto largo de la carga (NRO DOC = Solped) |
| | `Recepción PROVISORIOS` | Histórico: identifica líneas ya recepcionadas (con Documento material) |
| | `Aprobadores` | Maestro marca / código PEP / responsable |
| Informe Real de Inversión (.xlsx) | `REAL <MES> <AÑO>` o `BASES <AÑO>` | Monto Neto Real por Pinta, Medio y Proveedor-Vehículo |

## Uso

1. Cargar ambos archivos en la barra lateral.
2. Elegir la hoja del Informe Real (si se usa `BASES`, elegir el mes).
3. Revisar la pestaña **Revisión**: líneas sin cruce, con cruce a revisar o con observaciones. El importe real puede corregirse en la tabla y se aplica a ambas salidas.
4. Descargar los dos Excel.

## Despliegue en Streamlit Community Cloud

1. Crear un repositorio en GitHub y subir el contenido de esta carpeta (sin planillas: el `.gitignore` excluye los `.xlsx`).
2. En [share.streamlit.io](https://share.streamlit.io) elegir *Create app*, seleccionar el repositorio, rama `main` y archivo `app.py`.
3. El entorno instala `requirements.txt` automáticamente. El tamaño máximo de carga está fijado en 100 MB en `.streamlit/config.toml`.

Ejecución local (opcional):

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Estructura

```
app.py                 Interfaz Streamlit
src/config.py          Parámetros, catálogos y homologaciones (editar aquí)
src/utils.py           Lectura de números/fechas SAP, normalización, similitud
src/loaders.py         Lectura y estandarización de pestañas
src/enlace.py          Enlace PROVISORIOS <-> Monitor Prov (PEP por posición)
src/cruce_real.py      Cruce de cada línea con el Informe Real
src/generador.py       Selección de líneas y armado de las hojas de salida
src/exportador.py      Escritura de los Excel con el formato original
tests/test_utils.py    Pruebas de reglas básicas (pytest)
```

## Mantenimiento mensual

- **Marca nueva o renombrada en el Informe Real**: si aparece en la pestaña *Homologación de marcas* como "Sin homologar", agregar la equivalencia en `ALIAS_MARCA_A_CODIGO` (`src/config.py`), con la Pinta tal como viene en el informe y el código de 5 caracteres del PEP.
- **Código de medio PEP nuevo**: agregarlo en `MEDIO_POR_CODIGO_PEP`.
- **Abreviatura o traducción nueva en los textos de carga**: agregarla en `SINONIMOS_VEHICULO`.
- **Umbrales**: `PUNTAJE_MINIMO`, `PUNTAJE_REVISAR`, `TOLERANCIA_REDONDEO` y `ALERTA_DESVIACION_PCT`.

## Validación

Con el histórico de la pestaña Recepción PROVISORIOS (febrero a julio 2026), la columna O generada coincide con la cargada manualmente en 91 % a 97 % de las líneas en CLP, según el mes. Las diferencias revisadas corresponden mayoritariamente a filas desplazadas o intercambiadas en el histórico manual y a líneas con el mismo vehículo repetido, donde la asignación entre ellas no es determinable con los datos disponibles (la app las marca como observación).
