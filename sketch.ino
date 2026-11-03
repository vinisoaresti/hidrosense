#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>

// 1. ATUALIZE COM O SEU WI-FI REAL (Obrigatório ser rede 2.4 GHz)
const char* ssid = "Vini";
const char* password = "naotemsenha";

// Configurações da agua-api
const char* serverName = "http://192.168.18.10:8000/telemetry"; // Atualize com sua URL do Ngrok
const String deviceId = "esp32-caixa-01"; 
const String deviceHash = "hash-legal";

// Pinos físicos no ESP32-WROOM-32 conectados ao JSN-SR04T V3.3
const int trigPin = 5;  // Ligue no pino RX (Trig) do JSN-SR04T
const int echoPin = 18; // Ligue no pino TX (Echo) do JSN-SR04T

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(trigPin, OUTPUT);
  // INPUT_PULLUP estabiliza o sinal de retorno em 3.3V no JSN-SR04T V3.3
  pinMode(echoPin, INPUT_PULLUP); 

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  Serial.print("Conectando ao WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nConectado ao WiFi!");
  Serial.print("IP do ESP32: ");
  Serial.println(WiFi.localIP());
}

void loop() {
  // 1. Aciona o sensor JSN-SR04T (pulso de 20us para transdutor à prova d'água)
  digitalWrite(trigPin, LOW);
  delayMicroseconds(5);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(20);
  digitalWrite(trigPin, LOW);

  // 2. Lê o tempo de retorno com timeout de 38ms (~6.5m) para não travar o ESP32
  long duration = pulseIn(echoPin, HIGH, 38000);
  float distance_cm = (duration * 0.0343) / 2.0;

  // Diagnóstico no Monitor Serial
  if (duration == 0) {
    Serial.println("Aviso: Sem leitura de eco (verifique fios RX/TX ou se o sensor está a mais de 25cm do alvo).");
  } else {
    Serial.print("Distância: ");
    Serial.print(distance_cm, 2);
    Serial.println(" cm");
  }

  // 3. Envia os dados consolidados para a agua-api via HTTPS
  if (WiFi.status() == WL_CONNECTED) {
    WiFiClientSecure client;
    client.setInsecure(); // Necessário no ESP32 físico para HTTPS (Webhook.site / Ngrok) sem certificado

    HTTPClient http;
    if (http.begin(client, serverName)) {
      // Cabeçalhos de segurança exigidos pela arquitetura
      http.addHeader("Content-Type", "application/json");
      http.addHeader("device-id", deviceId);
      http.addHeader("hash", deviceHash);
      
      // Payload JSON com o dado bruto (2 casas decimais)
      String payload = "{\"distance_cm\": " + String(distance_cm, 2) + "}";
      int httpResponseCode = http.POST(payload);
      
      Serial.print("HTTP Response: ");
      Serial.println(httpResponseCode);
      if (httpResponseCode < 0) {
        Serial.print("Erro HTTP: ");
        Serial.println(http.errorToString(httpResponseCode));
      }
      http.end();
    }
  } else {
    Serial.println("WiFi desconectado! Tentando reconectar...");
    WiFi.reconnect();
  }
  
  // Pausa de 10 segundos entre os envios
  delay(10000); 
}