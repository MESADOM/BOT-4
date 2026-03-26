from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import LONG as modulo_long_trend
import SORT as modulo_short_trend


# ============================================================
# CONFIG
# ============================================================

VERSION_SISTEMA = "2.2.6"

BASE_DIR = Path(__file__).resolve().parent
DIR_DATOS = BASE_DIR / "datos"

RUTA_QQQ = DIR_DATOS / "QQQ.csv"
RUTA_QQQ3 = DIR_DATOS / "QQQ3.csv"
RUTA_VIX = DIR_DATOS / "VIX.csv"

GUARDAR_RESULTADOS = False
RUTA_SALIDA_OPERACIONES = DIR_DATOS / "operaciones_generadas.csv"
RUTA_SALIDA_RESUMEN = DIR_DATOS / "resumen_anual_generado.csv"

CAPITAL_INICIAL_EUR = 1000.0
COMISION_POR_OPERACION_EUR = 2.0
UMBRAL_SALIDA_LOGICA_A_EUR = -200.0
MOTIVO_SALIDA_LOGICA_A = "STOP_200_RET20_NEG"

PERIODO_MEDIA_LARGA = 50
DIAS_CONFIRMACION_ENTRADA = 1

REGIMEN_AGRESIVO = "AGRESIVO"
REGIMEN_DEFENSIVO = "DEFENSIVO"

FRECUENCIA_REVISION_REGIMEN = "SEMANAL"
PERIODO_SMA200_REGIMEN = 200
VENTANA_RETORNO_63_REGIMEN = 63
VENTANA_CRUCES_SMA50_REGIMEN = 20
UMBRAL_CRUCES_SERRUCHO = 4

SIZING_AGRESIVO_PORCENTAJE_CAPITAL = 0.90
SIZING_AGRESIVO_MAX_UNIDADES = 50

SIZING_DEFENSIVO_PORCENTAJE_CAPITAL = 0.70
SIZING_DEFENSIVO_MAX_UNIDADES = 10

REGIMEN_LONG_TREND = "LONG_TREND"
REGIMEN_SHORT_TREND = "SHORT_TREND"
REGIMEN_MEAN_REVERSION = "MEAN_REVERSION"
REGIMEN_NO_TRADE = "NO_TRADE"

MODO_META = "LONG_SHORT"


# ============================================================
# DATACLASSES
# ============================================================

@dataclass
class OperacionAbierta:
    modulo_activo: str
    fecha_entrada: datetime
    precio_entrada: float
    unidades: int
    capital_antes_eur: float
    maximo_desde_entrada: float
    minimo_desde_entrada: float
    senal_entrada: str
    regimen_entrada: str
    porcentaje_objetivo_entrada: float
    max_unidades_entrada: int
    capital_objetivo_entrada_eur: float
    capital_invertido_entrada_eur: float
    porcentaje_real_invertido: float
    entrada_capada_por_unidades: bool
    score_regimen: int
    qqq_close_referencia: float
    sma200_referencia: Optional[float]
    qqq_mayor_sma200: Optional[bool]
    retorno_63: Optional[float]
    retorno_estado: str
    cruces_sma50_ventana: int
    cruces_estado: str
    motivo_regimen: str
    score_regimen_2: float
    etiqueta_regimen_2: str
    sizing_2: float
    score_funcionamiento_sistema_2: float
    funcionamiento_sistema_2: str
    ajuste_funcionamiento: float
    sizing_final: float
    modo_defensa: str
    ret20: Optional[float]
    atr20_pct: Optional[float]
    max_ganancia_flotante_eur: float
    max_perdida_flotante_eur: float
    max_ganancia_flotante_pct: float
    max_perdida_flotante_pct: float
    fecha_max_ganancia_flotante: datetime
    fecha_max_perdida_flotante: datetime


@dataclass
class EstadoDiagnostico:
    entradas_capadas_por_unidades: int = 0
    senales_no_ejecutadas_sin_capital: int = 0


# ============================================================
# UTILIDADES
# ============================================================

def _parse_num_es(value: str) -> float:
    value = str(value).strip().replace(".", "").replace(",", ".")
    return float(value)


def _to_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value

    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def cargar_csv(ruta: Path) -> List[Dict[str, Any]]:
    with open(ruta, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return [dict(r) for r in reader]


def guardar_csv(ruta: Path, filas: List[Dict[str, Any]]) -> None:
    if not filas:
        with open(ruta, "w", encoding="utf-8-sig", newline="") as fh:
            fh.write("")
        return

    columnas = list(filas[0].keys())
    with open(ruta, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columnas)
        writer.writeheader()
        for fila in filas:
            serializada = {}
            for k, v in fila.items():
                if isinstance(v, datetime):
                    serializada[k] = v.strftime("%Y-%m-%d")
                else:
                    serializada[k] = v
            writer.writerow(serializada)


def _serializar_tsv(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, bool):
        return "VERDADERO" if value else "FALSO"
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return ""
        texto = f"{value:.10f}".rstrip("0").rstrip(".")
        texto = "0" if texto in {"", "-0"} else texto
        return texto
    return str(value).replace("\t", " ").replace("\r", " ").replace("\n", " ")


def imprimir_tabla_tsv(columnas: List[str], filas: List[Dict[str, Any]]) -> None:
    print("\t".join(columnas))
    for fila in filas:
        print("\t".join(_serializar_tsv(fila.get(columna)) for columna in columnas))


def construir_tablas_salida(resultados: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    resumen_anual = []
    for fila in resultados["resumen_anual"]:
        resumen_anual.append(
            {
                "Año": fila.get("anio"),
                "Operaciones": fila.get("operaciones"),
                "Beneficio neto €": fila.get("beneficio_neto_eur"),
                "Ganadoras": fila.get("ganadoras"),
                "Perdedoras": fila.get("perdedoras"),
                "Win rate %": fila.get("win_rate_pct"),
                "Capital acumulado €": fila.get("capital_acumulado_eur"),
                "Rentabilidad %": fila.get("rentabilidad_pct"),
                "Drawdown máx %": fila.get("drawdown_max_pct"),
            }
        )

    operaciones_ordenadas = sorted(
        resultados["operaciones"],
        key=lambda fila: (fila["fecha_entrada"], fila["fecha_salida"]),
    )
    detalle_operaciones = []
    for fila in operaciones_ordenadas:
        detalle_operaciones.append(
            {
                "Fecha entrada": fila.get("fecha_entrada"),
                "Fecha salida": fila.get("fecha_salida"),
                "Modulo activo": (
                    "LONG_TREND"
                    if "QQQ>SMA50" in str(fila.get("senal_entrada", ""))
                    else "SHORT_TREND"
                    if "QQQ<SMA50" in str(fila.get("senal_entrada", ""))
                    else ""
                ),
                "Señal entrada": fila.get("senal_entrada"),
                "Precio entrada": fila.get("precio_entrada"),
                "Precio salida": fila.get("precio_salida"),
                "Unidades": fila.get("unidades"),
                "Motivo salida": fila.get("motivo_salida"),
                "Beneficio acumulado €": fila.get("beneficio_acumulado_eur"),
                "Rentabilidad %": fila.get("rentabilidad_pct"),
                "Capital acumulado €": fila.get("capital_acumulado_eur"),
                "Beneficio neto €": fila.get("beneficio_neto_eur"),
                "Regimen vigente": fila.get("regimen_vigente", fila.get("regimen_entrada")),
                "Motivo régimen": fila.get("motivo_regimen"),
                "Porcentaje capital usado": fila.get("porcentaje_real_invertido"),
                "Capital antes entrada €": fila.get("capital_antes_eur"),
                "QQQ > SMA200": fila.get("qqq_mayor_sma200"),
                "Retorno 63": fila.get("retorno_63"),
                "ret20": fila.get("ret20"),
                "atr20_pct": fila.get("atr20_pct"),
                "Cruces SMA50": fila.get("cruces_sma50_ventana"),
                "Score regimen 2": fila.get("score_regimen_2"),
                "Etiqueta regimen 2": fila.get("etiqueta_regimen_2"),
                "Sizing 2": fila.get("sizing_2"),
                "Score funcionamiento sistema 2": fila.get("score_funcionamiento_sistema_2"),
                "Funcionamiento sistema 2": fila.get("funcionamiento_sistema_2"),
                "Ajuste funcionamiento": fila.get("ajuste_funcionamiento"),
                "Sizing final": fila.get("sizing_final"),
                "Modo defensa": fila.get("modo_defensa"),
                "Max ganancia flotante €": fila.get("max_ganancia_flotante_eur"),
                "Max perdida flotante €": fila.get("max_perdida_flotante_eur"),
                "Max ganancia flotante %": fila.get("max_ganancia_flotante_pct"),
                "Max perdida flotante %": fila.get("max_perdida_flotante_pct"),
                "Fecha max ganancia flotante": fila.get("fecha_max_ganancia_flotante"),
                "Fecha max perdida flotante": fila.get("fecha_max_perdida_flotante"),
            }
        )

    return resumen_anual, detalle_operaciones


def _normalizar_columnas(rows: Iterable[Dict[str, Any]], prefijo: str) -> List[Dict[str, Any]]:
    normalizadas: List[Dict[str, Any]] = []

    for raw in rows:
        row = {str(k).strip().lower(): v for k, v in raw.items()}

        if prefijo == "qqq" and len(row) == 1:
            unico = next(iter(row.values()))
            campos = next(csv.reader([str(unico)]))
            if len(campos) >= 5:
                normalizadas.append(
                    {
                        "fecha": _to_datetime(campos[0]),
                        f"{prefijo}_close": float(campos[1]),
                        f"{prefijo}_open": float(campos[2]),
                        f"{prefijo}_high": float(campos[3]),
                        f"{prefijo}_low": float(campos[4]),
                    }
                )
            continue

        out: Dict[str, Any] = {}
        for col, val in row.items():
            if col in ["date", "fecha", '"fecha"', '"date']:
                out["fecha"] = _to_datetime(val)
            elif col in ["close", "adj close", "adj_close", "cierre", "último", "ultimo"]:
                if prefijo == "qqq":
                    out[f"{prefijo}_close"] = float(str(val).replace(",", "."))
                else:
                    out[f"{prefijo}_close"] = _parse_num_es(val)
            elif col in ["open", "apertura"]:
                if prefijo == "qqq":
                    out[f"{prefijo}_open"] = float(str(val).replace(",", "."))
                else:
                    out[f"{prefijo}_open"] = _parse_num_es(val)
            elif col in ["high", "max", "alto", "máximo"]:
                if prefijo == "qqq":
                    out[f"{prefijo}_high"] = float(str(val).replace(",", "."))
                else:
                    out[f"{prefijo}_high"] = _parse_num_es(val)
            elif col in ["low", "min", "bajo", "mínimo"]:
                if prefijo == "qqq":
                    out[f"{prefijo}_low"] = float(str(val).replace(",", "."))
                else:
                    out[f"{prefijo}_low"] = _parse_num_es(val)

        if out.get("fecha") is not None:
            normalizadas.append(out)

    normalizadas.sort(key=lambda x: x["fecha"])
    return normalizadas


# ============================================================
# INDICADORES
# ============================================================

def _media_simple(closes: List[float], idx: int, periodo: int) -> Optional[float]:
    if idx + 1 < periodo:
        return None
    inicio = idx - periodo + 1
    return sum(closes[inicio : idx + 1]) / float(periodo)


def _clasificar_retorno_63(retorno_63: Optional[float]) -> str:
    if retorno_63 is None:
        return "NEUTRAL"
    if retorno_63 > 0.03:
        return "POSITIVO"
    if retorno_63 < -0.05:
        return "NEGATIVO"
    return "NEUTRAL"


def _clasificar_cruces(cruces_sma50: int) -> str:
    return "ALTO" if cruces_sma50 > UMBRAL_CRUCES_SERRUCHO else "NO_ALTO"


def _calcular_cruces_sma50(closes: List[float], idx: int) -> int:
    cruces = 0
    inicio = max(0, idx - VENTANA_CRUCES_SMA50_REGIMEN + 1)
    ultimo_signo: Optional[int] = None

    for j in range(inicio, idx + 1):
        sma50 = _media_simple(closes, j, 50)
        if sma50 is None:
            continue

        diff = closes[j] - sma50
        signo_actual = 0
        if diff > 0:
            signo_actual = 1
        elif diff < 0:
            signo_actual = -1

        if ultimo_signo is not None and signo_actual != 0 and signo_actual != ultimo_signo:
            cruces += 1

        if signo_actual != 0:
            ultimo_signo = signo_actual

    return cruces


def calcular_ret20(closes: List[float], idx: int) -> Optional[float]:
    if idx < 20:
        return None
    close_pasado = closes[idx - 20]
    if close_pasado <= 0:
        return None
    return (closes[idx] / close_pasado) - 1.0


def calcular_atr20_pct(
    highs: List[Optional[float]],
    lows: List[Optional[float]],
    closes: List[float],
    idx: int,
) -> Optional[float]:
    if idx < 20:
        return None

    true_ranges: List[float] = []
    for j in range(idx - 19, idx + 1):
        high = highs[j]
        low = lows[j]
        close_prev = closes[j - 1] if j > 0 else None
        if high is None or low is None or close_prev is None:
            return None
        tr = max(high - low, abs(high - close_prev), abs(low - close_prev))
        true_ranges.append(tr)

    atr20 = sum(true_ranges) / 20.0
    close_actual = closes[idx]
    if close_actual <= 0:
        return None
    return atr20 / close_actual


def clasificar_etiqueta_regimen_2(score_regimen_2: float) -> str:
    if score_regimen_2 >= 3:
        return "FAVORABLE"
    if score_regimen_2 >= 0:
        return "MIXTO"
    return "PROBLEMATICO"


def degradar_etiqueta_regimen_2_si_impulso_corto_debil(
    etiqueta_regimen_2: str,
    ret20: Optional[float],
    retorno_63: Optional[float],
) -> str:
    if ret20 is None or retorno_63 is None:
        return etiqueta_regimen_2
    if ret20 <= 0 and retorno_63 < 0.02:
        if etiqueta_regimen_2 == "FAVORABLE":
            return "MIXTO"
        if etiqueta_regimen_2 == "MIXTO":
            return "PROBLEMATICO"
    return etiqueta_regimen_2


def calcular_score_regimen_2(
    qqq_close: float,
    sma50: Optional[float],
    sma200_actual: Optional[float],
    sma200_hace_20: Optional[float],
    retorno_63: Optional[float],
    ret20: Optional[float],
    atr20_pct: Optional[float],
    cruces_sma50_ventana: Optional[int],
) -> Dict[str, Any]:
    sma200_pendiente_20_2: Optional[float] = None
    if sma200_actual is not None and sma200_hace_20 is not None and sma200_hace_20 > 0:
        sma200_pendiente_20_2 = (sma200_actual / sma200_hace_20) - 1.0

    dist_sma50_2: Optional[float] = None
    if sma50 is not None and sma50 > 0:
        dist_sma50_2 = (qqq_close / sma50) - 1.0

    aceleracion_2: Optional[float] = None
    if ret20 is not None and retorno_63 is not None:
        aceleracion_2 = ret20 - retorno_63

    score_nivel_2 = 0
    if sma200_actual is not None and sma200_pendiente_20_2 is not None:
        if qqq_close > sma200_actual and sma200_pendiente_20_2 > 0:
            score_nivel_2 = 2
        elif qqq_close > sma200_actual and sma200_pendiente_20_2 <= 0:
            score_nivel_2 = 1
        elif qqq_close <= sma200_actual and sma200_pendiente_20_2 > 0:
            score_nivel_2 = -1
        else:
            score_nivel_2 = -2

    score_velocidad_2 = 0
    if retorno_63 is not None:
        if retorno_63 > 0.08:
            score_velocidad_2 = 2
        elif retorno_63 > 0.03:
            score_velocidad_2 = 1
        elif retorno_63 >= 0:
            score_velocidad_2 = 0
        elif retorno_63 > -0.03:
            score_velocidad_2 = -1
        else:
            score_velocidad_2 = -2

    score_aceleracion_2 = 0
    if aceleracion_2 is not None:
        if aceleracion_2 > 0.03:
            score_aceleracion_2 = 1
        elif aceleracion_2 < -0.02:
            score_aceleracion_2 = -1

    score_cruces_2 = 0
    if cruces_sma50_ventana is not None:
        if cruces_sma50_ventana <= 1:
            score_cruces_2 = 1
        elif cruces_sma50_ventana >= 4:
            score_cruces_2 = -1

    score_atr_2 = 0
    if atr20_pct is not None:
        if atr20_pct < 0.025:
            score_atr_2 = 1
        elif atr20_pct > 0.04:
            score_atr_2 = -1

    score_extension_2 = 0
    if dist_sma50_2 is not None and dist_sma50_2 > 0.10:
        score_extension_2 = -1

    score_regimen_2 = (
        score_nivel_2
        + score_velocidad_2
        + score_aceleracion_2
        + score_cruces_2
        + score_atr_2
        + score_extension_2
    )
    etiqueta_regimen_2 = clasificar_etiqueta_regimen_2(score_regimen_2)
    etiqueta_regimen_2 = degradar_etiqueta_regimen_2_si_impulso_corto_debil(
        etiqueta_regimen_2=etiqueta_regimen_2,
        ret20=ret20,
        retorno_63=retorno_63,
    )

    sizing_2 = 0.80
    if etiqueta_regimen_2 == "FAVORABLE":
        sizing_2 = 1.00
    elif etiqueta_regimen_2 == "MIXTO":
        sizing_2 = 0.90

    return {
        "sma200_pendiente_20_2": sma200_pendiente_20_2,
        "dist_sma50_2": dist_sma50_2,
        "aceleracion_2": aceleracion_2,
        "score_nivel_2": score_nivel_2,
        "score_velocidad_2": score_velocidad_2,
        "score_aceleracion_2": score_aceleracion_2,
        "score_cruces_2": score_cruces_2,
        "score_atr_2": score_atr_2,
        "score_extension_2": score_extension_2,
        "score_regimen_2": score_regimen_2,
        "etiqueta_regimen_2": etiqueta_regimen_2,
        "sizing_2": sizing_2,
    }


def clasificar_funcionamiento_sistema_2(score: float) -> str:
    if score >= 2:
        return "FUERTE"
    if score >= 0:
        return "NEUTRO"
    return "DEBIL"


def calcular_score_funcionamiento_sistema_2(operaciones_previas: List[Dict[str, Any]]) -> float:
    previas = operaciones_previas[-4:]
    rent_previas = [float(x.get("rentabilidad_pct", 0.0)) for x in previas]
    if not previas:
        return 0.0

    media = sum(rent_previas) / len(rent_previas)
    maximo = max(rent_previas)
    minimo = min(rent_previas)
    ganadoras = sum(1 for r in rent_previas if r > 0)

    score_a = 2.0 if media > 2 else 1.0 if media > 0 else -1.0
    score_b = 1.0 if maximo > 10 else 0.5 if maximo > 5 else 0.0
    score_c = -2.0 if minimo < -8 else -1.0 if minimo < -5 else 0.0
    score_d = 1.0 if ganadoras >= 3 else -1.0 if ganadoras <= 1 else 0.0
    score_e = -1.0 if rent_previas[-1] < -3 else 0.0
    score_f = -1.0 if len(rent_previas) >= 2 and rent_previas[-1] < 0 and rent_previas[-2] < 0 else 0.0
    return score_a + score_b + score_c + score_d + score_e + score_f


def calcular_ajuste_funcionamiento(funcionamiento_sistema_2: str) -> float:
    if funcionamiento_sistema_2 == "FUERTE":
        return 1.00
    if funcionamiento_sistema_2 == "NEUTRO":
        return 0.95
    return 0.80


def calcular_sizing_final(sizing_2: float, ajuste_funcionamiento: float) -> float:
    return float(sizing_2) * float(ajuste_funcionamiento)


def calcular_modo_defensa(etiqueta_regimen_2: str, funcionamiento_sistema_2: str) -> str:
    if etiqueta_regimen_2 == "PROBLEMATICO" and funcionamiento_sistema_2 == "DEBIL":
        return "DEFENSA_FUERTE"
    if etiqueta_regimen_2 == "PROBLEMATICO" or funcionamiento_sistema_2 == "DEBIL":
        return "DEFENSA"
    return "NORMAL"


def inicializar_metricas_flotantes_operacion(operacion: OperacionAbierta) -> None:
    operacion.max_ganancia_flotante_eur = 0.0
    operacion.max_perdida_flotante_eur = 0.0
    operacion.max_ganancia_flotante_pct = 0.0
    operacion.max_perdida_flotante_pct = 0.0
    operacion.fecha_max_ganancia_flotante = operacion.fecha_entrada
    operacion.fecha_max_perdida_flotante = operacion.fecha_entrada


def calcular_resultado_flotante_operacion(
    operacion: OperacionAbierta,
    precio_actual: float,
) -> Tuple[float, float]:
    if operacion.modulo_activo == REGIMEN_LONG_TREND:
        beneficio_flotante_eur = (precio_actual - operacion.precio_entrada) * operacion.unidades
    elif operacion.modulo_activo == REGIMEN_SHORT_TREND:
        beneficio_flotante_eur = (operacion.precio_entrada - precio_actual) * operacion.unidades
    else:
        beneficio_flotante_eur = 0.0

    capital_ref = operacion.capital_antes_eur
    beneficio_flotante_pct = (beneficio_flotante_eur / capital_ref) * 100.0 if capital_ref > 0 else 0.0
    return beneficio_flotante_eur, beneficio_flotante_pct


def actualizar_metricas_flotantes_operacion(
    operacion: OperacionAbierta,
    fecha_actual: datetime,
    precio_actual: float,
) -> None:
    beneficio_eur, beneficio_pct = calcular_resultado_flotante_operacion(operacion, precio_actual)
    if beneficio_eur > operacion.max_ganancia_flotante_eur:
        operacion.max_ganancia_flotante_eur = beneficio_eur
        operacion.max_ganancia_flotante_pct = beneficio_pct
        operacion.fecha_max_ganancia_flotante = fecha_actual
    if beneficio_eur < operacion.max_perdida_flotante_eur:
        operacion.max_perdida_flotante_eur = beneficio_eur
        operacion.max_perdida_flotante_pct = beneficio_pct
        operacion.fecha_max_perdida_flotante = fecha_actual


def calcular_variables_regimen(closes: List[float], idx: int) -> Dict[str, Any]:
    close_actual = closes[idx]
    sma200 = _media_simple(closes, idx, PERIODO_SMA200_REGIMEN)

    retorno_63: Optional[float] = None
    if idx >= VENTANA_RETORNO_63_REGIMEN:
        close_pasado = closes[idx - VENTANA_RETORNO_63_REGIMEN]
        if close_pasado > 0:
            retorno_63 = (close_actual / close_pasado) - 1.0

    cruces_sma50 = _calcular_cruces_sma50(closes, idx)

    return {
        "qqq_sobre_sma200": None if sma200 is None else close_actual > sma200,
        "sma200": sma200,
        "retorno_63": retorno_63,
        "cruces_sma50": cruces_sma50,
    }


def evaluar_regimen_sizing(variables_regimen: Dict[str, Any], qqq_close_referencia: float) -> Dict[str, Any]:
    qqq_sobre_sma200 = variables_regimen.get("qqq_sobre_sma200")
    sma200 = variables_regimen.get("sma200")
    retorno_63 = variables_regimen.get("retorno_63")
    cruces_sma50 = int(variables_regimen.get("cruces_sma50", 0) or 0)

    retorno_estado = _clasificar_retorno_63(retorno_63)
    cruces_estado = _clasificar_cruces(cruces_sma50)

    if qqq_sobre_sma200 is False and retorno_estado == "NEGATIVO" and cruces_estado == "ALTO":
        regimen = REGIMEN_DEFENSIVO
        motivo = "DEFENSIVO: qqq<sma200, retorno_63 negativo y cruces altos"
    elif qqq_sobre_sma200 is True and cruces_estado != "ALTO":
        regimen = REGIMEN_AGRESIVO
        motivo = "AGRESIVO: qqq>sma200 y cruces no altos; retorno neutral o ligeramente negativo no invalida"
    elif qqq_sobre_sma200 is True and retorno_estado == "POSITIVO":
        regimen = REGIMEN_AGRESIVO
        motivo = "AGRESIVO: qqq>sma200 y retorno positivo"
    else:
        regimen = REGIMEN_AGRESIVO
        motivo = "AGRESIVO: caso intermedio resuelto a favor del sesgo alcista"

    score = 0
    if qqq_sobre_sma200 is True:
        score += 1
    elif qqq_sobre_sma200 is False:
        score -= 1

    if retorno_estado == "POSITIVO":
        score += 1
    elif retorno_estado == "NEGATIVO":
        score -= 1

    if cruces_estado == "ALTO":
        score -= 1

    return {
        "regimen": regimen,
        "score_regimen": score,
        "qqq_close_referencia": qqq_close_referencia,
        "sma200_referencia": sma200,
        "qqq_mayor_sma200": qqq_sobre_sma200,
        "retorno_63": retorno_63,
        "retorno_estado": retorno_estado,
        "cruces_sma50_ventana": cruces_sma50,
        "cruces_estado": cruces_estado,
        "motivo_regimen": motivo,
    }


def detectar_meta_regimen(hoy: Dict[str, Any]) -> str:
    if MODO_META == "LONG_ONLY":
        return REGIMEN_LONG_TREND

    if MODO_META == "SHORT_ONLY":
        return REGIMEN_SHORT_TREND

    if MODO_META == "LONG_SHORT":
        qqq_mayor_sma200 = hoy.get("qqq_mayor_sma200")
        retorno_estado = hoy.get("retorno_estado")
        cruces_estado = hoy.get("cruces_estado")

        if qqq_mayor_sma200 is True and retorno_estado in ("POSITIVO", "NEUTRAL") and cruces_estado != "ALTO":
            return REGIMEN_LONG_TREND

        if qqq_mayor_sma200 is False and retorno_estado == "NEGATIVO":
            return REGIMEN_SHORT_TREND

        return REGIMEN_NO_TRADE

    return REGIMEN_NO_TRADE


def obtener_parametros_sizing(regimen: str) -> Tuple[float, int]:
    if regimen == REGIMEN_AGRESIVO:
        return float(SIZING_AGRESIVO_PORCENTAJE_CAPITAL), int(SIZING_AGRESIVO_MAX_UNIDADES)
    return float(SIZING_DEFENSIVO_PORCENTAJE_CAPITAL), int(SIZING_DEFENSIVO_MAX_UNIDADES)


def _es_momento_revision_regimen(
    fecha_actual: datetime,
    ultima_revision_semana: Optional[Tuple[int, int]],
) -> bool:
    if FRECUENCIA_REVISION_REGIMEN != "SEMANAL":
        return True
    semana_actual = (fecha_actual.isocalendar().year, fecha_actual.isocalendar().week)
    return semana_actual != ultima_revision_semana


# ============================================================
# PREPARAR DATOS
# ============================================================

def preparar_datos(
    df_qqq: List[Dict[str, Any]],
    df_qqq3: List[Dict[str, Any]],
    df_vix: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    qqq = _normalizar_columnas(df_qqq, prefijo="qqq")
    qqq3 = _normalizar_columnas(df_qqq3, prefijo="qqq3")
    _ = _normalizar_columnas(df_vix, prefijo="vix")

    map_qqq = {r["fecha"]: r for r in qqq}
    map_qqq3 = {r["fecha"]: r for r in qqq3}
    fechas = sorted(set(map_qqq.keys()) | set(map_qqq3.keys()))

    rows: List[Dict[str, Any]] = []
    closes: List[float] = []
    highs: List[Optional[float]] = []
    lows: List[Optional[float]] = []
    ultimas_senales: List[bool] = []
    ultimas_senales_short: List[bool] = []
    n_confirmacion = max(1, int(DIAS_CONFIRMACION_ENTRADA))

    regimen_sizing_actual = REGIMEN_DEFENSIVO
    ultima_semana_revisada: Optional[Tuple[int, int]] = None
    ultima_info_regimen: Dict[str, Any] = {
        "score_regimen": 0,
        "qqq_close_referencia": 0.0,
        "sma200_referencia": None,
        "qqq_mayor_sma200": None,
        "retorno_63": None,
        "retorno_estado": "NEUTRAL",
        "cruces_sma50_ventana": 0,
        "cruces_estado": "NO_ALTO",
        "motivo_regimen": "estado inicial",
        "score_regimen_2": 0.0,
        "etiqueta_regimen_2": "MIXTO",
        "sizing_2": 0.90,
    }

    for fecha in fechas:
        row = {
            "fecha": fecha,
            "qqq_close": map_qqq.get(fecha, {}).get("qqq_close"),
            "qqq3_close": map_qqq3.get(fecha, {}).get("qqq3_close"),
            "qqq3_open": map_qqq3.get(fecha, {}).get("qqq3_open"),
            "regimen_sizing": regimen_sizing_actual,
            "score_regimen": ultima_info_regimen["score_regimen"],
            "qqq_close_referencia": ultima_info_regimen["qqq_close_referencia"],
            "sma200_referencia": ultima_info_regimen["sma200_referencia"],
            "qqq_mayor_sma200": ultima_info_regimen["qqq_mayor_sma200"],
            "retorno_63": ultima_info_regimen["retorno_63"],
            "retorno_estado": ultima_info_regimen["retorno_estado"],
            "cruces_sma50_ventana": ultima_info_regimen["cruces_sma50_ventana"],
            "cruces_estado": ultima_info_regimen["cruces_estado"],
            "motivo_regimen": ultima_info_regimen["motivo_regimen"],
            "meta_regimen": REGIMEN_NO_TRADE,
            "ret20": None,
            "atr20_pct": None,
            "score_regimen_2": ultima_info_regimen.get("score_regimen_2", 0.0),
            "etiqueta_regimen_2": ultima_info_regimen.get("etiqueta_regimen_2", "MIXTO"),
            "sizing_2": ultima_info_regimen.get("sizing_2", 0.90),
        }

        close = row["qqq_close"]
        if close is None:
            row["qqq_media_larga"] = None
            row["senal_base_on"] = False
            row["senal_confirmada"] = False
            row["senal_short_base_on"] = False
            row["senal_short_confirmada"] = False
            row["sma50"] = None
            rows.append(row)
            continue

        close_float = float(close)
        closes.append(close_float)
        highs.append(map_qqq.get(fecha, {}).get("qqq_high"))
        lows.append(map_qqq.get(fecha, {}).get("qqq_low"))

        sma50 = _media_simple(closes, len(closes) - 1, PERIODO_MEDIA_LARGA)
        ret20 = calcular_ret20(closes, len(closes) - 1)
        atr20_pct = calcular_atr20_pct(highs, lows, closes, len(closes) - 1)

        row["sma50"] = sma50
        row["qqq_media_larga"] = sma50
        row["senal_base_on"] = bool(sma50 is not None and close_float > sma50)
        row["senal_short_base_on"] = bool(sma50 is not None and close_float < sma50)

        ultimas_senales.append(bool(row["senal_base_on"]))
        if len(ultimas_senales) > n_confirmacion:
            ultimas_senales.pop(0)
        row["senal_confirmada"] = len(ultimas_senales) == n_confirmacion and all(ultimas_senales)

        ultimas_senales_short.append(bool(row["senal_short_base_on"]))
        if len(ultimas_senales_short) > n_confirmacion:
            ultimas_senales_short.pop(0)
        row["senal_short_confirmada"] = len(ultimas_senales_short) == n_confirmacion and all(ultimas_senales_short)

        if _es_momento_revision_regimen(fecha, ultima_semana_revisada):
            variables_regimen = calcular_variables_regimen(closes=closes, idx=len(closes) - 1)
            info_regimen = evaluar_regimen_sizing(variables_regimen, qqq_close_referencia=close_float)

            regimen_sizing_actual = info_regimen["regimen"]
            ultima_info_regimen = info_regimen
            ultima_semana_revisada = (fecha.isocalendar().year, fecha.isocalendar().week)

        row["regimen_sizing"] = regimen_sizing_actual
        row["score_regimen"] = ultima_info_regimen["score_regimen"]
        row["qqq_close_referencia"] = close_float
        row["sma200_referencia"] = ultima_info_regimen["sma200_referencia"]
        row["qqq_mayor_sma200"] = ultima_info_regimen["qqq_mayor_sma200"]
        row["retorno_63"] = ultima_info_regimen["retorno_63"]
        row["retorno_estado"] = ultima_info_regimen["retorno_estado"]
        row["cruces_sma50_ventana"] = ultima_info_regimen["cruces_sma50_ventana"]
        row["cruces_estado"] = ultima_info_regimen["cruces_estado"]
        row["motivo_regimen"] = ultima_info_regimen["motivo_regimen"]
        row["ret20"] = ret20
        row["atr20_pct"] = atr20_pct

        sma200_actual = _media_simple(closes, len(closes) - 1, PERIODO_SMA200_REGIMEN)
        sma200_hace_20: Optional[float] = None
        idx_sma_20 = len(closes) - 1 - 20
        if idx_sma_20 >= 0:
            sma200_hace_20 = _media_simple(closes, idx_sma_20, PERIODO_SMA200_REGIMEN)

        regimen_2 = calcular_score_regimen_2(
            qqq_close=close_float,
            sma50=sma50,
            sma200_actual=sma200_actual,
            sma200_hace_20=sma200_hace_20,
            retorno_63=row.get("retorno_63"),
            ret20=ret20,
            atr20_pct=atr20_pct,
            cruces_sma50_ventana=row.get("cruces_sma50_ventana"),
        )
        row.update(regimen_2)

        row["meta_regimen"] = detectar_meta_regimen(row)

        rows.append(row)

    return rows


# ============================================================
# ENGINE
# ============================================================

def ejecutar_meta_bot(
    df: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]]:
    capital_actual = float(CAPITAL_INICIAL_EUR)
    operacion_abierta: Optional[OperacionAbierta] = None
    operaciones: List[Dict[str, Any]] = []
    diagnostico = EstadoDiagnostico()
    activaciones_logica_a = 0

    entrada_pendiente = False
    salida_pendiente = False
    motivo_salida_pendiente = ""
    modulo_entrada_pendiente = ""
    regimen_entrada_pendiente = REGIMEN_DEFENSIVO
    diagnostico_entrada_pendiente: Dict[str, Any] = {}
    ultima_fecha_salida_ejecutada: Optional[datetime] = None

    for i in range(len(df) - 1):
        hoy = df[i]
        manana = df[i + 1]

        qqq_close_hoy = hoy.get("qqq_close")
        qqq3_close_hoy = hoy.get("qqq3_close")
        qqq3_open_manana = manana.get("qqq3_open")

        if qqq_close_hoy is None or qqq3_close_hoy is None or qqq3_open_manana is None:
            continue

        qqq3_open_manana = float(qqq3_open_manana)

        if salida_pendiente and operacion_abierta is not None:
            precio_salida = qqq3_open_manana
            maximo_flotante = max(operacion_abierta.maximo_desde_entrada, precio_salida)
            minimo_flotante = min(operacion_abierta.minimo_desde_entrada, precio_salida)

            if operacion_abierta.modulo_activo == REGIMEN_LONG_TREND:
                beneficio_bruto = (precio_salida - operacion_abierta.precio_entrada) * operacion_abierta.unidades
                max_ganancia_flotante_eur = (
                    (maximo_flotante - operacion_abierta.precio_entrada) * operacion_abierta.unidades
                ) - COMISION_POR_OPERACION_EUR
                max_perdida_flotante_eur = (
                    (minimo_flotante - operacion_abierta.precio_entrada) * operacion_abierta.unidades
                ) - COMISION_POR_OPERACION_EUR
            elif operacion_abierta.modulo_activo == REGIMEN_SHORT_TREND:
                beneficio_bruto = (operacion_abierta.precio_entrada - precio_salida) * operacion_abierta.unidades
                max_ganancia_flotante_eur = (
                    (operacion_abierta.precio_entrada - minimo_flotante) * operacion_abierta.unidades
                ) - COMISION_POR_OPERACION_EUR
                max_perdida_flotante_eur = (
                    (operacion_abierta.precio_entrada - maximo_flotante) * operacion_abierta.unidades
                ) - COMISION_POR_OPERACION_EUR
            else:
                beneficio_bruto = 0.0
                max_ganancia_flotante_eur = 0.0
                max_perdida_flotante_eur = 0.0
            beneficio_neto = beneficio_bruto - COMISION_POR_OPERACION_EUR

            rentabilidad_pct = 0.0
            max_ganancia_flotante_pct = 0.0
            max_perdida_flotante_pct = 0.0
            if operacion_abierta.capital_antes_eur > 0:
                rentabilidad_pct = (beneficio_neto / operacion_abierta.capital_antes_eur) * 100.0
                max_ganancia_flotante_pct = (
                    max_ganancia_flotante_eur / operacion_abierta.capital_antes_eur
                ) * 100.0
                max_perdida_flotante_pct = (
                    max_perdida_flotante_eur / operacion_abierta.capital_antes_eur
                ) * 100.0

            # Incluir explícitamente el punto final real de salida en el recorrido flotante.
            fecha_salida_real = manana["fecha"]
            if beneficio_neto > operacion_abierta.max_ganancia_flotante_eur:
                operacion_abierta.max_ganancia_flotante_eur = beneficio_neto
                operacion_abierta.fecha_max_ganancia_flotante = fecha_salida_real
            if beneficio_neto < operacion_abierta.max_perdida_flotante_eur:
                operacion_abierta.max_perdida_flotante_eur = beneficio_neto
                operacion_abierta.fecha_max_perdida_flotante = fecha_salida_real

            if rentabilidad_pct > operacion_abierta.max_ganancia_flotante_pct:
                operacion_abierta.max_ganancia_flotante_pct = rentabilidad_pct
                operacion_abierta.fecha_max_ganancia_flotante = fecha_salida_real
            if rentabilidad_pct < operacion_abierta.max_perdida_flotante_pct:
                operacion_abierta.max_perdida_flotante_pct = rentabilidad_pct
                operacion_abierta.fecha_max_perdida_flotante = fecha_salida_real

            capital_actual += beneficio_neto
            beneficio_acumulado_eur = capital_actual - CAPITAL_INICIAL_EUR
            if operacion_abierta.modulo_activo == REGIMEN_LONG_TREND:
                stop_trailing = modulo_long_trend.calcular_stop_trailing(operacion_abierta)
            elif operacion_abierta.modulo_activo == REGIMEN_SHORT_TREND:
                stop_trailing = modulo_short_trend.calcular_stop_trailing(operacion_abierta)
            else:
                stop_trailing = 0.0

            operaciones.append(
                {
                    "version_sistema": VERSION_SISTEMA,
                    "modulo_activo": operacion_abierta.modulo_activo,
                    "fecha_entrada": operacion_abierta.fecha_entrada,
                    "fecha_salida": manana["fecha"],
                    "precio_entrada": round(operacion_abierta.precio_entrada, 6),
                    "precio_salida": round(precio_salida, 6),
                    "unidades": int(operacion_abierta.unidades),
                    "senal_entrada": operacion_abierta.senal_entrada,
                    "motivo_salida": motivo_salida_pendiente,
                    "regimen_entrada": operacion_abierta.regimen_entrada,
                    "regimen_vigente": operacion_abierta.regimen_entrada,
                    "score_regimen": operacion_abierta.score_regimen,
                    "qqq_close_referencia": operacion_abierta.qqq_close_referencia,
                    "sma200_referencia": operacion_abierta.sma200_referencia,
                    "qqq_mayor_sma200": operacion_abierta.qqq_mayor_sma200,
                    "retorno_63": operacion_abierta.retorno_63,
                    "retorno_estado": operacion_abierta.retorno_estado,
                    "cruces_sma50_ventana": operacion_abierta.cruces_sma50_ventana,
                    "cruces_estado": operacion_abierta.cruces_estado,
                    "motivo_regimen": operacion_abierta.motivo_regimen,
                    "score_regimen_2": round(float(operacion_abierta.score_regimen_2), 4),
                    "etiqueta_regimen_2": operacion_abierta.etiqueta_regimen_2,
                    "sizing_2": round(float(operacion_abierta.sizing_2), 4),
                    "score_funcionamiento_sistema_2": round(float(operacion_abierta.score_funcionamiento_sistema_2), 4),
                    "funcionamiento_sistema_2": operacion_abierta.funcionamiento_sistema_2,
                    "ajuste_funcionamiento": round(float(operacion_abierta.ajuste_funcionamiento), 4),
                    "sizing_final": round(float(operacion_abierta.sizing_final), 4),
                    "modo_defensa": operacion_abierta.modo_defensa,
                    "ret20": operacion_abierta.ret20,
                    "atr20_pct": operacion_abierta.atr20_pct,
                    "porcentaje_objetivo_entrada": round(operacion_abierta.porcentaje_objetivo_entrada, 4),
                    "max_unidades_entrada": int(operacion_abierta.max_unidades_entrada),
                    "capital_objetivo_entrada_eur": round(operacion_abierta.capital_objetivo_entrada_eur, 2),
                    "capital_invertido_entrada_eur": round(operacion_abierta.capital_invertido_entrada_eur, 2),
                    "porcentaje_real_invertido": round(operacion_abierta.porcentaje_real_invertido, 4),
                    "entrada_capada_por_unidades": bool(operacion_abierta.entrada_capada_por_unidades),
                    "beneficio_neto_eur": round(beneficio_neto, 2),
                    "beneficio_acumulado_eur": round(beneficio_acumulado_eur, 2),
                    "rentabilidad_pct": round(rentabilidad_pct, 4),
                    "max_ganancia_flotante_pct": round(max_ganancia_flotante_pct, 4),
                    "max_perdida_flotante_pct": round(max_perdida_flotante_pct, 4),
                    "capital_antes_eur": round(operacion_abierta.capital_antes_eur, 2),
                    "capital_acumulado_eur": round(capital_actual, 2),
                    "maximo_desde_entrada": round(maximo_flotante, 6),
                    "minimo_desde_entrada": round(minimo_flotante, 6),
                    "stop_trailing": round(stop_trailing, 6),
                    "max_ganancia_flotante_eur": round(operacion_abierta.max_ganancia_flotante_eur, 2),
                    "max_perdida_flotante_eur": round(operacion_abierta.max_perdida_flotante_eur, 2),
                    "max_ganancia_flotante_pct": round(operacion_abierta.max_ganancia_flotante_pct, 4),
                    "max_perdida_flotante_pct": round(operacion_abierta.max_perdida_flotante_pct, 4),
                    "fecha_max_ganancia_flotante": operacion_abierta.fecha_max_ganancia_flotante,
                    "fecha_max_perdida_flotante": operacion_abierta.fecha_max_perdida_flotante,
                }
            )

            ultima_fecha_salida_ejecutada = manana["fecha"]
            operacion_abierta = None
            salida_pendiente = False
            motivo_salida_pendiente = ""

        if entrada_pendiente and operacion_abierta is None:
            porcentaje_objetivo, max_unidades = obtener_parametros_sizing(regimen_entrada_pendiente)
            sizing_final = float(diagnostico_entrada_pendiente.get("sizing_final", 1.0) or 1.0)

            capital_objetivo = capital_actual * porcentaje_objetivo * sizing_final
            unidades_teoricas = int(math.floor(capital_objetivo / qqq3_open_manana)) if qqq3_open_manana > 0 else 0
            unidades = max(0, min(unidades_teoricas, max_unidades))
            entrada_capada = unidades_teoricas > max_unidades

            coste_entrada = unidades * qqq3_open_manana + COMISION_POR_OPERACION_EUR
            capital_invertido = unidades * qqq3_open_manana
            porcentaje_real = (capital_invertido / capital_actual) if capital_actual > 0 else 0.0

            if entrada_capada:
                diagnostico.entradas_capadas_por_unidades += 1

            if unidades > 0 and coste_entrada <= capital_actual:
                operacion_abierta = OperacionAbierta(
                    modulo_activo=modulo_entrada_pendiente,
                    fecha_entrada=manana["fecha"],
                    precio_entrada=qqq3_open_manana,
                    unidades=unidades,
                    capital_antes_eur=capital_actual,
                    maximo_desde_entrada=qqq3_open_manana,
                    minimo_desde_entrada=qqq3_open_manana,
                    senal_entrada=(
                        f"QQQ>SMA{PERIODO_MEDIA_LARGA} x{DIAS_CONFIRMACION_ENTRADA}"
                        if modulo_entrada_pendiente == REGIMEN_LONG_TREND
                        else f"QQQ<SMA{PERIODO_MEDIA_LARGA} x{DIAS_CONFIRMACION_ENTRADA}"
                    ),
                    regimen_entrada=regimen_entrada_pendiente,
                    porcentaje_objetivo_entrada=porcentaje_objetivo,
                    max_unidades_entrada=max_unidades,
                    capital_objetivo_entrada_eur=capital_objetivo,
                    capital_invertido_entrada_eur=capital_invertido,
                    porcentaje_real_invertido=porcentaje_real,
                    entrada_capada_por_unidades=entrada_capada,
                    score_regimen=int(diagnostico_entrada_pendiente.get("score_regimen", 0)),
                    qqq_close_referencia=float(diagnostico_entrada_pendiente.get("qqq_close_referencia", 0.0)),
                    sma200_referencia=diagnostico_entrada_pendiente.get("sma200_referencia"),
                    qqq_mayor_sma200=diagnostico_entrada_pendiente.get("qqq_mayor_sma200"),
                    retorno_63=diagnostico_entrada_pendiente.get("retorno_63"),
                    retorno_estado=str(diagnostico_entrada_pendiente.get("retorno_estado", "NEUTRAL")),
                    cruces_sma50_ventana=int(diagnostico_entrada_pendiente.get("cruces_sma50_ventana", 0)),
                    cruces_estado=str(diagnostico_entrada_pendiente.get("cruces_estado", "NO_ALTO")),
                    motivo_regimen=str(diagnostico_entrada_pendiente.get("motivo_regimen", "")),
                    score_regimen_2=float(diagnostico_entrada_pendiente.get("score_regimen_2", 0.0) or 0.0),
                    etiqueta_regimen_2=str(diagnostico_entrada_pendiente.get("etiqueta_regimen_2", "MIXTO")),
                    sizing_2=float(diagnostico_entrada_pendiente.get("sizing_2", 0.90) or 0.90),
                    score_funcionamiento_sistema_2=float(
                        diagnostico_entrada_pendiente.get("score_funcionamiento_sistema_2", 0.0) or 0.0
                    ),
                    funcionamiento_sistema_2=str(
                        diagnostico_entrada_pendiente.get("funcionamiento_sistema_2", "NEUTRO")
                    ),
                    ajuste_funcionamiento=float(
                        diagnostico_entrada_pendiente.get("ajuste_funcionamiento", 0.95) or 0.95
                    ),
                    sizing_final=sizing_final,
                    modo_defensa=str(diagnostico_entrada_pendiente.get("modo_defensa", "NORMAL")),
                    ret20=diagnostico_entrada_pendiente.get("ret20"),
                    atr20_pct=diagnostico_entrada_pendiente.get("atr20_pct"),
                    max_ganancia_flotante_eur=0.0,
                    max_perdida_flotante_eur=0.0,
                    max_ganancia_flotante_pct=0.0,
                    max_perdida_flotante_pct=0.0,
                    fecha_max_ganancia_flotante=manana["fecha"],
                    fecha_max_perdida_flotante=manana["fecha"],
                )
                inicializar_metricas_flotantes_operacion(operacion_abierta)
            else:
                diagnostico.senales_no_ejecutadas_sin_capital += 1

            entrada_pendiente = False
            modulo_entrada_pendiente = ""

        if operacion_abierta is None:
            meta_regimen_hoy = hoy.get("meta_regimen", REGIMEN_NO_TRADE)

            if meta_regimen_hoy == REGIMEN_LONG_TREND:
                permitir_entrada = modulo_long_trend.permite_entrada(
                    hoy=hoy,
                    ultima_fecha_salida_ejecutada=ultima_fecha_salida_ejecutada,
                    operaciones=operaciones,
                )

                if permitir_entrada:
                    score_funcionamiento = calcular_score_funcionamiento_sistema_2(operaciones)
                    funcionamiento = clasificar_funcionamiento_sistema_2(score_funcionamiento)
                    ajuste_funcionamiento = calcular_ajuste_funcionamiento(funcionamiento)
                    sizing_2 = float(hoy.get("sizing_2", 0.90) or 0.90)
                    sizing_final = calcular_sizing_final(sizing_2, ajuste_funcionamiento)
                    etiqueta_regimen_2 = str(hoy.get("etiqueta_regimen_2", "MIXTO"))
                    modo_defensa = calcular_modo_defensa(etiqueta_regimen_2, funcionamiento)
                    entrada_pendiente = True
                    modulo_entrada_pendiente = REGIMEN_LONG_TREND
                    regimen_entrada_pendiente = str(hoy.get("regimen_sizing", REGIMEN_DEFENSIVO))
                    diagnostico_entrada_pendiente = {
                        "score_regimen": hoy.get("score_regimen", 0),
                        "qqq_close_referencia": hoy.get("qqq_close_referencia", hoy.get("qqq_close", 0.0) or 0.0),
                        "sma200_referencia": hoy.get("sma200_referencia"),
                        "qqq_mayor_sma200": hoy.get("qqq_mayor_sma200"),
                        "retorno_63": hoy.get("retorno_63"),
                        "retorno_estado": hoy.get("retorno_estado", "NEUTRAL"),
                        "cruces_sma50_ventana": hoy.get("cruces_sma50_ventana", 0),
                        "cruces_estado": hoy.get("cruces_estado", "NO_ALTO"),
                        "motivo_regimen": hoy.get("motivo_regimen", ""),
                        "score_regimen_2": hoy.get("score_regimen_2", 0.0),
                        "etiqueta_regimen_2": etiqueta_regimen_2,
                        "sizing_2": sizing_2,
                        "score_funcionamiento_sistema_2": score_funcionamiento,
                        "funcionamiento_sistema_2": funcionamiento,
                        "ajuste_funcionamiento": ajuste_funcionamiento,
                        "sizing_final": sizing_final,
                        "modo_defensa": modo_defensa,
                        "ret20": hoy.get("ret20"),
                        "atr20_pct": hoy.get("atr20_pct"),
                    }

            elif meta_regimen_hoy == REGIMEN_SHORT_TREND:
                permitir_entrada = modulo_short_trend.permite_entrada(
                    hoy=hoy,
                    ultima_fecha_salida_ejecutada=ultima_fecha_salida_ejecutada,
                    operaciones=operaciones,
                )

                if permitir_entrada:
                    score_funcionamiento = calcular_score_funcionamiento_sistema_2(operaciones)
                    funcionamiento = clasificar_funcionamiento_sistema_2(score_funcionamiento)
                    ajuste_funcionamiento = calcular_ajuste_funcionamiento(funcionamiento)
                    sizing_2 = float(hoy.get("sizing_2", 0.90) or 0.90)
                    sizing_final = calcular_sizing_final(sizing_2, ajuste_funcionamiento)
                    etiqueta_regimen_2 = str(hoy.get("etiqueta_regimen_2", "MIXTO"))
                    modo_defensa = calcular_modo_defensa(etiqueta_regimen_2, funcionamiento)
                    entrada_pendiente = True
                    modulo_entrada_pendiente = REGIMEN_SHORT_TREND
                    regimen_entrada_pendiente = str(hoy.get("regimen_sizing", REGIMEN_DEFENSIVO))
                    diagnostico_entrada_pendiente = {
                        "score_regimen": hoy.get("score_regimen", 0),
                        "qqq_close_referencia": hoy.get("qqq_close_referencia", hoy.get("qqq_close", 0.0) or 0.0),
                        "sma200_referencia": hoy.get("sma200_referencia"),
                        "qqq_mayor_sma200": hoy.get("qqq_mayor_sma200"),
                        "retorno_63": hoy.get("retorno_63"),
                        "retorno_estado": hoy.get("retorno_estado", "NEUTRAL"),
                        "cruces_sma50_ventana": hoy.get("cruces_sma50_ventana", 0),
                        "cruces_estado": hoy.get("cruces_estado", "NO_ALTO"),
                        "motivo_regimen": hoy.get("motivo_regimen", ""),
                        "score_regimen_2": hoy.get("score_regimen_2", 0.0),
                        "etiqueta_regimen_2": etiqueta_regimen_2,
                        "sizing_2": sizing_2,
                        "score_funcionamiento_sistema_2": score_funcionamiento,
                        "funcionamiento_sistema_2": funcionamiento,
                        "ajuste_funcionamiento": ajuste_funcionamiento,
                        "sizing_final": sizing_final,
                        "modo_defensa": modo_defensa,
                        "ret20": hoy.get("ret20"),
                        "atr20_pct": hoy.get("atr20_pct"),
                    }

        else:
            actualizar_metricas_flotantes_operacion(
                operacion=operacion_abierta,
                fecha_actual=hoy["fecha"],
                precio_actual=float(qqq3_close_hoy),
            )
            ret20_hoy = hoy.get("ret20")
            beneficio_flotante_eur = 0.0
            if operacion_abierta.modulo_activo == REGIMEN_LONG_TREND:
                beneficio_flotante_eur = (
                    (float(qqq3_close_hoy) - operacion_abierta.precio_entrada) * operacion_abierta.unidades
                ) - COMISION_POR_OPERACION_EUR
            elif operacion_abierta.modulo_activo == REGIMEN_SHORT_TREND:
                beneficio_flotante_eur = (
                    (operacion_abierta.precio_entrada - float(qqq3_close_hoy)) * operacion_abierta.unidades
                ) - COMISION_POR_OPERACION_EUR

            condicion_logica_a = (
                ret20_hoy is not None
                and float(ret20_hoy) < 0
                and beneficio_flotante_eur <= UMBRAL_SALIDA_LOGICA_A_EUR
            )
            if condicion_logica_a:
                salida_pendiente = True
                activaciones_logica_a += 1
                motivo_salida_pendiente = MOTIVO_SALIDA_LOGICA_A
                continue

            if operacion_abierta.modulo_activo == REGIMEN_LONG_TREND:
                motivo_salida = modulo_long_trend.senal_salida(hoy, operacion_abierta)
                if motivo_salida:
                    salida_pendiente = True
                    motivo_salida_pendiente = motivo_salida
            elif operacion_abierta.modulo_activo == REGIMEN_SHORT_TREND:
                motivo_salida = modulo_short_trend.senal_salida(hoy, operacion_abierta)
                if motivo_salida:
                    salida_pendiente = True
                    motivo_salida_pendiente = motivo_salida

    operaciones_ordenadas = sorted(operaciones, key=lambda x: x["fecha_salida"])

    diagnostico_regimen_tsv: List[Dict[str, Any]] = []
    for op in operaciones_ordenadas:
        diagnostico_regimen_tsv.append(
            {
                "fecha_entrada": op["fecha_entrada"],
                "fecha_salida": op["fecha_salida"],
                "modulo_activo": op["modulo_activo"],
                "regimen_vigente": op["regimen_vigente"],
                "score_regimen": op.get("score_regimen", 0),
                "qqq_close_referencia": round(float(op.get("qqq_close_referencia", 0.0)), 6),
                "sma200_referencia": None if op.get("sma200_referencia") is None else round(float(op["sma200_referencia"]), 6),
                "qqq_mayor_sma200": op.get("qqq_mayor_sma200"),
                "retorno_63": None if op.get("retorno_63") is None else round(float(op["retorno_63"]), 6),
                "retorno_estado": op.get("retorno_estado"),
                "cruces_sma50_ventana": op.get("cruces_sma50_ventana", 0),
                "cruces_estado": op.get("cruces_estado"),
                "porcentaje_capital_objetivo": op.get("porcentaje_objetivo_entrada"),
                "max_unidades_regimen": op.get("max_unidades_entrada"),
                "unidades_ejecutadas": op.get("unidades"),
                "capital_objetivo": op.get("capital_objetivo_entrada_eur"),
                "capital_invertido_real": op.get("capital_invertido_entrada_eur"),
                "porcentaje_real_invertido": op.get("porcentaje_real_invertido"),
                "entrada_capada_por_max_unidades": op.get("entrada_capada_por_unidades"),
                "motivo_regimen": op.get("motivo_regimen", ""),
            }
        )

    metricas = crear_metricas_diagnosticas(operaciones_ordenadas, diagnostico)
    metricas["activaciones_logica_a"] = activaciones_logica_a
    resumen_regimen = crear_resumen_regimen(operaciones_ordenadas)

    return operaciones_ordenadas, metricas, diagnostico_regimen_tsv, resumen_regimen


# ============================================================
# RESUMENES
# ============================================================

def crear_resumen_regimen(df_operaciones: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}

    for regimen in [REGIMEN_AGRESIVO, REGIMEN_DEFENSIVO]:
        ops = [op for op in df_operaciones if op.get("regimen_vigente") == regimen]
        total = round(sum(float(op.get("beneficio_neto_eur", 0.0)) for op in ops), 2)
        out[regimen] = {
            "operaciones": len(ops),
            "beneficio_neto_total": total,
            "beneficio_medio_por_operacion": round(total / len(ops), 4) if ops else 0.0,
        }

    return out


def crear_resumen_anual(df_operaciones: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not df_operaciones:
        return []

    by_year: Dict[int, List[Dict[str, Any]]] = {}
    for op in df_operaciones:
        anio = op["fecha_salida"].year
        by_year.setdefault(anio, []).append(op)

    resumen: List[Dict[str, Any]] = []

    for anio in sorted(by_year.keys()):
        ops = by_year[anio]
        operaciones = len(ops)
        ganadoras = sum(1 for op in ops if op["beneficio_neto_eur"] > 0)
        perdedoras = operaciones - ganadoras
        beneficio_neto = round(sum(op["beneficio_neto_eur"] for op in ops), 2)

        win_rate = round((ganadoras / operaciones * 100.0) if operaciones else 0.0, 4)
        rentabilidad = round((beneficio_neto / CAPITAL_INICIAL_EUR) * 100.0, 4)

        curva = [float(op["capital_acumulado_eur"]) for op in ops]
        pico = 0.0
        dd_min = 0.0
        for valor in curva:
            pico = max(pico, valor)
            if pico > 0:
                dd = ((valor - pico) / pico) * 100.0
                dd_min = min(dd_min, dd)

        ops_agresivo = [op for op in ops if op.get("regimen_entrada") == REGIMEN_AGRESIVO]
        ops_defensivo = [op for op in ops if op.get("regimen_entrada") == REGIMEN_DEFENSIVO]

        resumen.append(
            {
                "version_sistema": VERSION_SISTEMA,
                "anio": anio,
                "operaciones": operaciones,
                "ganadoras": ganadoras,
                "perdedoras": perdedoras,
                "win_rate_pct": win_rate,
                "beneficio_neto_eur": beneficio_neto,
                "rentabilidad_pct": rentabilidad,
                "drawdown_max_pct": round(dd_min, 4),
                "operaciones_agresivo": len(ops_agresivo),
                "operaciones_defensivo": len(ops_defensivo),
                "beneficio_neto_agresivo_eur": round(sum(op["beneficio_neto_eur"] for op in ops_agresivo), 2),
                "beneficio_neto_defensivo_eur": round(sum(op["beneficio_neto_eur"] for op in ops_defensivo), 2),
                "capital_acumulado_eur": round(float(ops[-1]["capital_acumulado_eur"]), 2),
            }
        )

    return resumen


def crear_metricas_diagnosticas(df_operaciones: List[Dict[str, Any]], estado: EstadoDiagnostico) -> Dict[str, Any]:
    total_ops = len(df_operaciones)
    unidades_medias = 0.0
    pct_real_medio = 0.0

    if total_ops > 0:
        unidades_medias = sum(float(op.get("unidades", 0)) for op in df_operaciones) / total_ops
        pct_real_medio = (
            sum(float(op.get("porcentaje_real_invertido", 0.0)) for op in df_operaciones) / total_ops
        ) * 100.0

    return {
        "unidades_medias_por_operacion": round(unidades_medias, 4),
        "porcentaje_medio_capital_real_invertido": round(pct_real_medio, 4),
        "entradas_capadas_por_limite_unidades": int(estado.entradas_capadas_por_unidades),
        "senales_no_ejecutadas_sin_capital": int(estado.senales_no_ejecutadas_sin_capital),
    }


# ============================================================
# MAIN
# ============================================================

def ejecutar_bot() -> Dict[str, Any]:
    df_qqq = cargar_csv(RUTA_QQQ)
    df_qqq3 = cargar_csv(RUTA_QQQ3)
    df_vix = cargar_csv(RUTA_VIX)

    df_base = preparar_datos(df_qqq=df_qqq, df_qqq3=df_qqq3, df_vix=df_vix)
    df_operaciones, metricas, diagnostico_regimen_tsv, resumen_regimen = ejecutar_meta_bot(df_base)
    df_resumen_anual = crear_resumen_anual(df_operaciones)

    if GUARDAR_RESULTADOS:
        guardar_csv(RUTA_SALIDA_OPERACIONES, df_operaciones)
        guardar_csv(RUTA_SALIDA_RESUMEN, df_resumen_anual)

    return {
        "version_bot": VERSION_SISTEMA,
        "datos_base": df_base,
        "operaciones": df_operaciones,
        "resumen_anual": df_resumen_anual,
        "metricas": metricas,
        "diagnostico_regimen": diagnostico_regimen_tsv,
        "resumen_regimen": resumen_regimen,
    }


if __name__ == "__main__":
    resultados = ejecutar_bot()
    tabla_resumen_anual, tabla_detalle_operaciones = construir_tablas_salida(resultados)

    print(f"Version sistema: {resultados['version_bot']}\n")
    imprimir_tabla_tsv(
        [
            "Año",
            "Operaciones",
            "Beneficio neto €",
            "Ganadoras",
            "Perdedoras",
            "Win rate %",
            "Capital acumulado €",
            "Rentabilidad %",
            "Drawdown máx %",
        ],
        tabla_resumen_anual,
    )
    print()
    imprimir_tabla_tsv(
        [
            "Fecha entrada",
            "Fecha salida",
            "Modulo activo",
            "Señal entrada",
            "Precio entrada",
            "Precio salida",
            "Unidades",
            "Motivo salida",
            "Beneficio acumulado €",
            "Rentabilidad %",
            "Capital acumulado €",
            "Beneficio neto €",
            "Regimen vigente",
            "Motivo régimen",
            "Porcentaje capital usado",
            "Capital antes entrada €",
            "QQQ > SMA200",
            "Retorno 63",
            "ret20",
            "atr20_pct",
            "Cruces SMA50",
            "Score regimen 2",
            "Etiqueta regimen 2",
            "Sizing 2",
            "Score funcionamiento sistema 2",
            "Funcionamiento sistema 2",
            "Ajuste funcionamiento",
            "Sizing final",
            "Modo defensa",
            "Max ganancia flotante €",
            "Max perdida flotante €",
            "Max ganancia flotante %",
            "Max perdida flotante %",
            "Fecha max ganancia flotante",
            "Fecha max perdida flotante",
        ],
        tabla_detalle_operaciones,
    )
