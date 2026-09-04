"""Trailing stop automático — plantilla genérica (cualquier símbolo, toda posición abierta presente y futura).

Mueve el SL a favor del precio siguiendo la estructura H1 (higher-low para BUY,
lower-high para SELL). Reglas duras, no negociables por este script:
  - NUNCA afloja un SL ya puesto (solo se mueve a favor).
  - NUNCA toca el TP (siempre omite el parámetro take_profit).
  - NUNCA abre, cierra ni cancela nada — únicamente modify_position(stop_loss=...).
  - Si una posición no tiene SL, le pone uno inicial de estructura (protección,
    no apertura de riesgo nuevo).

Patrón de excepción HITL (ver HITL-EXCEPTION.md): este script mueve el SL SIN
pedir confirmación por movimiento — a cambio, notifica cada ajuste por Telegram
en tiempo casi real, y respeta un kill switch por archivo. Todo lo demás (abrir,
cerrar, aflojar SL, tocar TP) sigue exigiendo confirmación humana explícita.

Apagado de emergencia: crear el archivo TRAILING_STOP_OFF (vacío, cualquier
contenido) en la misma carpeta del script — se revisa en cada ciclo y al arrancar.

Uso: python trailing_stop.py
(pensado para lanzarse por tarea programada en el horario de sesión del símbolo
configurado; corre en loop revisando cada INTERVALO_SEG segundos).
"""
import io
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

import pandas as pd
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "conexiones"))
load_dotenv(RAIZ / ".env")

from metatrader_client import MT5Client  # noqa: E402 — provisto por el paquete metatrader-mcp-server

# ── Configuración (ajustar por instrumento/broker) ──────────────────────────
SIMBOLO        = os.getenv("TRAILING_SYMBOL", "SYMBOL_HERE")
INTERVALO_SEG  = int(os.getenv("TRAILING_INTERVAL_SEC", 15 * 60))
ZONA_HORARIA   = ZoneInfo(os.getenv("TRAILING_TZ", "America/New_York"))
SESION_INICIO  = dtime(*[int(x) for x in os.getenv("TRAILING_SESSION_START", "9:30").split(":")])
SESION_FIN     = dtime(*[int(x) for x in os.getenv("TRAILING_SESSION_END", "16:00").split(":")])
BUFFER_PTS     = float(os.getenv("TRAILING_BUFFER_PTS", 30))     # colchón bajo/sobre el pivote de estructura H1
MARGEN_PRECIO  = float(os.getenv("TRAILING_MIN_DISTANCE", 20))   # no fijar SL a menos de esta distancia del precio actual
KILL_SWITCH    = RAIZ / "TRAILING_STOP_OFF"


def enviar_telegram(texto: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chats = [c.strip() for c in os.getenv("TELEGRAM_CHAT_IDS", "").split(",") if c.strip()]
    if not token or not chats:
        print("AVISO: Telegram no configurado — aviso solo en log")
        return
    for chat in chats:
        try:
            payload = {"chat_id": chat, "text": texto, "parse_mode": "HTML"}
            datos = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=datos, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10)
        except Exception as exc:
            print(f"AVISO: envío a {chat} falló: {exc}")


def en_sesion(ahora: datetime) -> bool:
    return ahora.weekday() < 5 and SESION_INICIO <= ahora.time() < SESION_FIN


def conectar() -> MT5Client:
    client = MT5Client({"login": int(os.getenv("LOGIN")),
                        "password": os.getenv("PASSWORD"),
                        "server": os.getenv("SERVER")})
    client.connect()
    return client


def pivote_low(h1_cerradas: pd.DataFrame) -> float | None:
    """Último mínimo pivote CONFIRMADO (low menor que la vela anterior y la siguiente)."""
    for i in range(len(h1_cerradas) - 2, 0, -1):
        lo   = h1_cerradas.iloc[i]["low"]
        prev = h1_cerradas.iloc[i - 1]["low"]
        nxt  = h1_cerradas.iloc[i + 1]["low"]
        if lo < prev and lo < nxt:
            return float(lo)
    return None


def pivote_high(h1_cerradas: pd.DataFrame) -> float | None:
    for i in range(len(h1_cerradas) - 2, 0, -1):
        hi   = h1_cerradas.iloc[i]["high"]
        prev = h1_cerradas.iloc[i - 1]["high"]
        nxt  = h1_cerradas.iloc[i + 1]["high"]
        if hi > prev and hi > nxt:
            return float(hi)
    return None


def aplicar(client: MT5Client, pid: int, nuevo_sl: float, sl_previo: float,
            tipo: str, entrada: float, precio_ref: float) -> None:
    r = client.order.modify_position(id=pid, stop_loss=nuevo_sl)
    ok = isinstance(r, dict) and not r.get("error", True)
    ahora = datetime.now(ZONA_HORARIA)
    accion = "SL inicial" if sl_previo == 0 else "Trailing"
    estado = "OK" if ok else "FALLO"
    previo_txt = "—" if sl_previo == 0 else f"{sl_previo:,.2f}"
    print(f"{ahora:%H:%M:%S} [{estado}] {accion} #{pid} {tipo} → SL {nuevo_sl:,.2f} (antes {previo_txt})")

    if ok:
        msg = (
            f"🔧 <b>{accion} SL · {SIMBOLO} #{pid}</b> · {ahora:%H:%M} {ZONA_HORARIA}\n\n"
            f"{tipo} · entrada <code>{entrada:,.2f}</code>\n"
            f"SL {'colocado' if sl_previo == 0 else 'movido'}: "
            f"{previo_txt}{' → ' if sl_previo != 0 else ''}<code>{nuevo_sl:,.2f}</code>\n"
            f"Precio actual <code>{precio_ref:,.2f}</code>\n\n"
            f"Automático (trailing stop) — solo mueve a favor, nunca cierra ni abre."
        )
        enviar_telegram(msg)
    else:
        enviar_telegram(f"⚠️ Trailing stop: fallo al mover SL de #{pid} — revisar manualmente.\n{r}")


def procesar(client: MT5Client) -> None:
    pos = client.order.get_all_positions()
    if pos is None or pos.empty:
        return
    pos = pos[pos["symbol"] == SIMBOLO]
    if pos.empty:
        return

    h1 = client.market.get_candles_latest(symbol_name=SIMBOLO, timeframe="H1", count=40)
    h1 = h1.sort_values("time").reset_index(drop=True)
    h1_cerradas = h1.iloc[:-1]   # excluir la vela en formación

    precio = client.market.get_symbol_price(SIMBOLO)
    bid, ask = float(precio["bid"]), float(precio["ask"])

    piv_low  = pivote_low(h1_cerradas)
    piv_high = pivote_high(h1_cerradas)

    for _, p in pos.iterrows():
        pid     = int(p["id"])
        tipo    = p["type"]
        entrada = float(p["open"])
        sl_raw  = p["stop_loss"]
        sl_actual = 0.0 if pd.isna(sl_raw) else float(sl_raw)

        if tipo == "BUY" and piv_low is not None:
            candidato = round(piv_low - BUFFER_PTS, 2)
            if candidato <= bid - MARGEN_PRECIO and (sl_actual == 0 or candidato > sl_actual):
                aplicar(client, pid, candidato, sl_actual, tipo, entrada, bid)
        elif tipo == "SELL" and piv_high is not None:
            candidato = round(piv_high + BUFFER_PTS, 2)
            if candidato >= ask + MARGEN_PRECIO and (sl_actual == 0 or candidato < sl_actual):
                aplicar(client, pid, candidato, sl_actual, tipo, entrada, ask)


def main() -> None:
    if SIMBOLO == "SYMBOL_HERE":
        sys.exit("Configura TRAILING_SYMBOL en .env antes de correr esto (ver .env.example).")

    ahora = datetime.now(ZONA_HORARIA)
    if ahora.weekday() >= 5:
        print("Fin de semana — sin sesión.")
        return
    if KILL_SWITCH.exists():
        print("Kill switch activo (TRAILING_STOP_OFF) — no arranco.")
        return

    client = conectar()
    print(f"Trailing stop activo · {SIMBOLO} · reviso cada {INTERVALO_SEG // 60} min hasta {SESION_FIN}")

    while True:
        ahora = datetime.now(ZONA_HORARIA)
        if ahora.time() >= SESION_FIN or ahora.weekday() >= 5:
            break
        if KILL_SWITCH.exists():
            print("Kill switch detectado durante la sesión — me detengo.")
            break
        if not en_sesion(ahora):
            time.sleep(60)
            continue
        try:
            procesar(client)
        except Exception as exc:
            print(f"AVISO: ciclo falló ({exc}) — reconectando en 15s")
            try:
                client.disconnect()
            except Exception:
                pass
            time.sleep(15)
            try:
                client = conectar()
            except Exception as exc2:
                print(f"AVISO: reconexión falló ({exc2}) — reintento en 60s")
                time.sleep(60)
            continue
        time.sleep(INTERVALO_SEG)

    client.disconnect()
    print("Sesión terminada.")


if __name__ == "__main__":
    main()
