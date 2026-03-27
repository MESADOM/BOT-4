# BOT-4: Arquitectura real (estrategia + IB + proceso continuo)

## Arquitectura única y consistente

- `META_BOT.py` → **núcleo de estrategia** (señales, filtros, sizing, backtest y generación de señal operativa).
- `ib_manager.py` → **capa IB** (conectividad, reintentos, control de posición, deduplicación, envío de órdenes y alertas Telegram).
- `run_paper_bot.py` → **proceso continuo** para Paper en Windows (bucle, manejo de señales de apagado, logs y cierre limpio).

> No hay arquitectura solapada paralela: la vía principal de ejecución real/paper es `META_BOT.py` + `ib_manager.py` + `run_paper_bot.py`.

## Requisitos

- Python 3.10+
- `ib_insync`
- IB Gateway en Paper (`127.0.0.1:4002` por defecto)

## Variables `.env` recomendadas

```env
IB_HOST=127.0.0.1
IB_PORT=4002
IB_CLIENT_ID=1
IB_TIMEOUT=8
IB_MAX_RETRIES=3
PAPER_LOOP_SECONDS=60
PAPER_LOG_LEVEL=INFO

# Alertas Telegram (opcionales)
TELEGRAM_BOT_TOKEN=xxxxx
TELEGRAM_CHAT_ID=xxxxx
```

## Ejecución

### 1) Backtest tradicional (Windows)

```powershell
python META_BOT.py
```

### 2) Proceso continuo Paper (Windows, recomendado para operativo)

```powershell
python run_paper_bot.py
```

Comportamiento del runner:
- bucle `while` continuo,
- supervisión de conexión (`ensure_connection()`),
- logs por ciclo,
- soporte de señales `SIGINT`/`SIGTERM`,
- apagado limpio (`manager.close()`).

## Mensajería Telegram

Las alertas se envían al ejecutar una orden de **APERTURA** (`ENTRY_*`) o **CIERRE** (`EXIT_*`) y contienen estado de IB (`ib_status`) y metadatos de operación.

## Checks mínimos

```powershell
python -m py_compile META_BOT.py run_paper_bot.py ib_manager.py LONG.py SORT.py
python -c "import META_BOT, run_paper_bot, ib_manager, LONG, SORT; print('imports-ok')"
python run_paper_bot.py
```

> El último comando requiere IB Gateway y datos CSV disponibles en `datos/`.
