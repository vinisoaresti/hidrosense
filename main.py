"""
Mock local da agua-api para receber telemetria de um ESP32.

Rotas aceitas (POST): "/" e "/telemetry"
Headers esperados: Content-Type: application/json, device-id, hash
Payload esperado:  {"distance_cm": <float>}

Rodar:  python main.py   (escuta em 0.0.0.0:8000)
"""

import json
import socket
from datetime import datetime
from typing import Optional

import uvicorn
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

HOST = "0.0.0.0"
PORT = 8000

EXPECTED_DEVICE_ID = "esp32-caixa-01"
EXPECTED_HASH = "hash-legal"

app = FastAPI(title="agua-api mock")


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _local_ip() -> str:
    """Descobre o IP local usado para sair na rede (não envia pacotes)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


async def _handle_telemetry(
    request: Request,
    device_id: Optional[str],
    hash_: Optional[str],
) -> JSONResponse:
    raw = await request.body()
    raw_text = raw.decode("utf-8", errors="replace")
    client = request.client.host if request.client else "?"

    distance: Optional[float] = None
    parse_error: Optional[str] = None
    try:
        data = json.loads(raw_text) if raw_text else {}
        if "distance_cm" not in data:
            parse_error = "campo 'distance_cm' ausente"
        else:
            distance = float(data["distance_cm"])
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        parse_error = f"JSON inválido: {e}"

    id_ok = "OK" if device_id == EXPECTED_DEVICE_ID else "DIFERENTE DO ESPERADO"
    hash_ok = "OK" if hash_ == EXPECTED_HASH else "DIFERENTE DO ESPERADO"

    print("=" * 60)
    print(f"[{_ts()}] POST {request.url.path}  de {client}")
    print(f"  Content-Type : {request.headers.get('content-type')}")
    print(f"  device-id    : {device_id!r}  ({id_ok})")
    print(f"  hash         : {hash_!r}  ({hash_ok})")
    print(f"  payload bruto: {raw_text}")
    if parse_error:
        print(f"  ERRO         : {parse_error}")
    else:
        print(f"  distance_cm  : {distance:.2f} cm")
    print("=" * 60, flush=True)

    if parse_error:
        return JSONResponse(
            status_code=400, content={"status": "error", "detail": parse_error}
        )
    return JSONResponse(
        status_code=200,
        content={"status": "received", "distance_cm": distance, "timestamp": _ts()},
    )


@app.post("/")
async def telemetry_root(
    request: Request,
    device_id: Optional[str] = Header(None, alias="device-id"),
    hash_: Optional[str] = Header(None, alias="hash"),
):
    return await _handle_telemetry(request, device_id, hash_)


@app.post("/telemetry")
async def telemetry(
    request: Request,
    device_id: Optional[str] = Header(None, alias="device-id"),
    hash_: Optional[str] = Header(None, alias="hash"),
):
    return await _handle_telemetry(request, device_id, hash_)


@app.get("/")
async def health():
    return {"status": "ok", "service": "agua-api mock"}


if __name__ == "__main__":
    ip = _local_ip()
    print(f"\n>> agua-api mock rodando em http://{ip}:{PORT}/telemetry")
    print(f">> Use no firmware: serverName = \"http://{ip}:{PORT}/telemetry\"\n")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
