"""
Mock local e servidor da agua-api para receber telemetria de um ESP32
e realizar o processamento metodológico dos cálculos de nível, volume,
percentual, variação de volume (ΔV) e vazão média (Q).

Rotas aceitas (POST): "/" e "/telemetry"
Headers esperados: Content-Type: application/json, device-id, hash
Payload esperado:  {"distance_cm": <float>}

Rodar:  python main.py   (escuta em 0.0.0.0:8000)
"""

import json
import math
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

app = FastAPI(title="agua-api mock - HidroSense")

# --- CONFIGURAÇÃO DA CAIXA D'ÁGUA HIPOTÉTICA DE 1.000 LITROS ---
RESERVATORIO_CONFIG = {
    "modo": 1,                      # 1 = Geometria Regular, 2 = Curva de Calibração
    "altura_util_cm": 80.0,         # H: Altura útil total em cm
    "capacidade_max_l": 1000.0,     # Capacidade máxima em litros
    
    # Modo I (Geometria Cilíndrica Hipotética para 1000L em H=80cm)
    # Raio r ≈ 0.63078 m -> Base ≈ 1.25 m² -> Volume max = 1.25 m² * 0.8 m = 1.0 m³ = 1000 L
    "raio_m": 0.63078, 
    
    # Para caixa retangular, preencher comprimento_m e largura_m (ex: C=1.25m, L=1.0m, H=0.8m)
    "comprimento_m": 0.0,
    "largura_m": 0.0,
    
    # Modo II: Tabela de calibração (caso a caixa seja irregular)
    "calib_h": [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0],
    "calib_v": [0.0, 35.0, 90.0, 170.0, 280.0, 430.0, 600.0, 800.0, 1000.0]
}

# Histórico em memória para armazenar o último estado por dispositivo (para ΔV e vazão)
historico_dispositivos = {}


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _local_ip() -> str:
    """Descobre o IP local usado para sair na rede."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def calcular_hidrologia(distance_cm: float, device_id: str) -> dict:
    """Aplica as fórmulas metodológicas do reservatório."""
    cfg = RESERVATORIO_CONFIG
    H = cfg["altura_util_cm"]
    
    # 1. Determinação da Altura da Água (h = H - d)
    h_cm = H - distance_cm
    if h_cm < 0.0:
        h_cm = 0.0
    elif h_cm > H:
        h_cm = H
        
    # 2. Cálculo do Volume
    volume_litros = 0.0
    if cfg["modo"] == 1:
        h_m = h_cm / 100.0
        if cfg["comprimento_m"] > 0 and cfg["largura_m"] > 0:
            v_m3 = cfg["comprimento_m"] * cfg["largura_m"] * h_m
        else:
            v_m3 = math.pi * (cfg["raio_m"] ** 2) * h_m
        volume_litros = v_m3 * 1000.0
    else:
        # Modo II: Interpolação Linear na Curva de Calibração
        hs = cfg["calib_h"]
        vs = cfg["calib_v"]
        if h_cm <= hs[0]:
            volume_litros = vs[0]
        elif h_cm >= hs[-1]:
            volume_litros = vs[-1]
        else:
            for i in range(len(hs) - 1):
                if hs[i] <= h_cm <= hs[i+1]:
                    h1, h2 = hs[i], hs[i+1]
                    v1, v2 = vs[i], vs[i+1]
                    volume_litros = v1 + ((h_cm - h1) / (h2 - h1)) * (v2 - v1)
                    break

    # Limites de segurança
    if volume_litros < 0.0:
        volume_litros = 0.0
    if volume_litros > cfg["capacidade_max_l"]:
        volume_litros = cfg["capacidade_max_l"]

    # 4. Percentual do Reservatório
    percentual = (volume_litros / cfg["capacidade_max_l"]) * 100.0

    # 5 & 6. Variação de Volume (ΔV) e Vazão Média Estimada (Q)
    agora = datetime.now()
    delta_v = 0.0
    vazao_l_min = 0.0

    if device_id in historico_dispositivos:
        ultimo = historico_dispositivos[device_id]
        vol_anterior = ultimo["volume"]
        tempo_anterior = ultimo["timestamp"]
        
        delta_v = volume_litros - vol_anterior
        delta_t_min = (agora - tempo_anterior).total_seconds() / 60.0
        
        if delta_t_min > 0:
            vazao_l_min = abs(delta_v) / delta_t_min

    # Atualiza o histórico
    historico_dispositivos[device_id] = {
        "volume": volume_litros,
        "timestamp": agora
    }

    return {
        "altura_agua_cm": round(h_cm, 2),
        "volume_litros": round(volume_litros, 2),
        "percentual": round(percentual, 1),
        "delta_v_litros": round(delta_v, 2),
        "vazao_l_min": round(vazao_l_min, 2)
    }


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
        print("=" * 60, flush=True)
        return JSONResponse(
            status_code=400, content={"status": "error", "detail": parse_error}
        )
    
    dev_id = device_id or EXPECTED_DEVICE_ID
    calculos = calcular_hidrologia(distance, dev_id)

    print(f"  distance_cm  : {distance:.2f} cm")
    print(f"  altura_água  : {calculos['altura_agua_cm']:.2f} cm")
    print(f"  volume       : {calculos['volume_litros']:.2f} L ({calculos['percentual']}%)")
    print(f"  ΔV           : {calculos['delta_v_litros']:.2f} L")
    print(f"  vazão média  : {calculos['vazao_l_min']:.2f} L/min")
    print("=" * 60, flush=True)

    return JSONResponse(
        status_code=200,
        content={
            "status": "received",
            "device_id": dev_id,
            "distance_cm": distance,
            **calculos,
            "timestamp": _ts()
        },
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
