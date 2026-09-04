# Claude Trading Safety Agent

Patrón de referencia: un agente de Claude Code operando una cuenta de trading
real vía MCP, con una única automatización de alta frecuencia (trailing stop)
que corre sin supervisión humana continua — y el diseño de seguridad que hace
eso aceptable.

**Esto NO es una estrategia de trading.** No incluye señales, niveles de
entrada, ni lógica de cuándo abrir una posición — eso se queda fuera a
propósito. Lo que sí incluye es la pieza de gestión de riesgo *después* de que
una posición ya existe, y el patrón de control humano alrededor de ella.

## Qué hay aquí

- **`conexiones/run_mt5_mcp.py`** — wrapper que lanza `metatrader-mcp-server`
  (MCP) leyendo credenciales de `.env`, para que nunca queden en `.mcp.json`.
- **`trailing_stop.py`** — mueve el stop loss a favor del precio siguiendo la
  estructura de velas H1 (pivote confirmado), con reglas duras no negociables
  (ver `HITL-EXCEPTION.md`).
- **`HITL-EXCEPTION.md`** — el patrón de diseño: cómo darle a un agente una
  excepción acotada a la regla de "nunca escribas sin confirmación", de forma
  que la excepción sea segura por construcción.

## Cómo se usa

1. `pip install -r requirements.txt`
2. Copia `.env.example` a `.env` y rellena tus credenciales de MT5 + Telegram.
3. Abre Claude Code en esta carpeta — `.mcp.json` conecta el servidor MCP de
   MetaTrader automáticamente.
4. Corre `python trailing_stop.py` manualmente, o prográmalo (Task Scheduler /
   cron) para que arranque al inicio de tu sesión de mercado.
5. Para detenerlo de emergencia sin tocar el proceso: crea un archivo vacío
   llamado `TRAILING_STOP_OFF` en esta carpeta.

## El patrón, en una frase

Un agente puede tener autonomía real sobre un sistema con dinero/datos reales
— siempre que la autonomía esté recortada a una sola acción reversible en una
sola dirección, notificada de inmediato, y con un apagado que no dependa de
tocar código.

---
*Extraído y genericizado de un sistema de trading real en uso — ver
`HITL-EXCEPTION.md` para el razonamiento completo detrás del diseño.*
