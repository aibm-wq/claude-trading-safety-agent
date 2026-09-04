# Patrón: excepción HITL acotada

La regla base de este proyecto (y de todo agente que opere una cuenta real) es:
**ninguna escritura sobre el sistema externo sin confirmación humana explícita.**

`trailing_stop.py` es la única excepción, y está diseñada para que la excepción
sea segura por construcción, no por promesa:

| Elemento | Por qué hace la excepción segura |
|---|---|
| **Alcance mínimo** | Solo puede llamar a una función: mover el stop loss. No puede abrir, cerrar, ni tocar el take profit — esas rutas ni siquiera existen en el código. |
| **Dirección única** | El nuevo SL solo se acepta si mejora el existente (`candidato > sl_actual` para BUY, lo inverso para SELL). Nunca afloja. |
| **Notificación en tiempo casi real** | Cada movimiento dispara un mensaje a Telegram — el humano se entera en minutos, no al final del día. |
| **Kill switch por archivo** | Crear un archivo vacío (`TRAILING_STOP_OFF`) detiene el script en el próximo ciclo, sin tocar código ni credenciales. Se revisa al arrancar y en cada iteración del loop. |
| **Documentado, no implícito** | La excepción se declara explícitamente (fecha, quién la aprobó, qué cubre y qué no) en vez de vivir como una suposición tácita en el código. |

## Cómo se ve documentada la excepción en la práctica

```
Excepción HITL confirmada por [responsable] el [fecha]: este script mueve el SL
SIN pedir confirmación por movimiento — a cambio, notifica cada ajuste por
Telegram para que quede enterado casi en tiempo real. La matriz HITL del
proyecto sigue vigente para todo lo demás (abrir, cerrar, aflojar SL, tocar TP).
```

## Por qué esto importa para cualquier agente de IA con acceso a un sistema real

Un agente con acceso de escritura a un sistema real (una cuenta de trading, un
CRM, un ERP) necesita, en algún punto, poder actuar sin esperar confirmación
para tareas de alta frecuencia — pedir aprobación cada 15 minutos no es
operable. La respuesta correcta no es "confía en el agente", es **reducir el
radio de la excepción hasta que sea seguro dejarla correr sola**: una sola
función, una sola dirección posible, aviso inmediato, y un botón de apagado
que no dependa de tocar el código en producción.

Este mismo patrón es reusable para cualquier automatización de alta frecuencia
que un agente de Claude Code necesite operar sin supervisión continua.
