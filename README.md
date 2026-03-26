# VERSION 2.2.7 PAPER

Adaptación mínima para operar en **Interactive Brokers Paper Trading** con **IB Gateway** en **Windows**.

## 1) Instalar dependencias (Windows)
```bat
python -m pip install -r requirements.txt
```

## 2) Configurar variables de entorno
1. Copia `.env.example` a `.env`.
2. Ajusta valores si hace falta:

```env
IB_HOST=127.0.0.1
IB_PORT=4002
IB_CLIENT_ID=1
```

- **Paper:** `IB_PORT=4002`
- **Real:** `IB_PORT=4001`

## 3) Arrancar IB Gateway
1. Abre **IB Gateway** en Windows.
2. Inicia sesión con cuenta Paper.
3. Verifica API habilitada en configuración de IB Gateway.
4. Confirma que escucha en `127.0.0.1:4002`.

## 4) Ejecutar bot en Windows
Opción rápida:
```bat
start_bot.bat
```

O manual:
```bat
python run_paper_bot.py
```

## 5) Autoarranque en Windows
### Opción A: Task Scheduler
1. Abrir **Task Scheduler** > **Create Task**.
2. Trigger: **At log on**.
3. Action: **Start a program**.
4. Program/script: ruta a `start_bot.bat`.
5. Marcar "Run whether user is logged on or not" si aplica.

### Opción B: NSSM
1. Instala NSSM.
2. Crea servicio apuntando a `python` con argumento `run_paper_bot.py`.
3. Configura inicio automático del servicio.

## Notas operativas
- `META_BOT.py` mantiene la estrategia como núcleo.
- `run_paper_bot.py` gestiona ejecución continua y apagado limpio.
- `ib_connection.py` encapsula conexión/reconexión y utilidades de envío de órdenes.
- IB Gateway debe estar abierto y autenticado para operar.
