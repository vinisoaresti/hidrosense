#include <WiFi.h>
#include <HTTPClient.h>

// Credenciais da rede simulada do Wokwi
const char* ssid = "Wokwi-GUEST";
const char* password = "";

// Configurações da agua-api
const char* serverName = "https://webhook.site/a6882307-e44e-4503-98cb-f3e17c6b2e6e"; // Atualize com sua URL do Ngrok
const String deviceId = "esp32-caixa-01"; 
const String deviceHash = "hash-legal";

// Pinos do sensor conectados no simulador
const int trigPin = 5;
const int echoPin = 18;

void setup() {
  Serial.begin(115200);
  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);

  WiFi.begin(ssid, password);
  Serial.print("Conectando ao WiFi...");
  while(WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nConectado ao WiFi!");
}

void loop() {
  // 1. Aciona o sensor ultrassônico
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  // 2. Calcula a distância física da lâmina d'água
  long duration = pulseIn(echoPin, HIGH);
  float distance_cm = duration * 0.034 / 2;

  Serial.print("Distância: ");
  Serial.print(distance_cm);
  Serial.println(" cm");

  // 3. Envia os dados consolidados para a agua-api
  if(WiFi.status() == WL_CONNECTED){
    HTTPClient http;
    http.begin(serverName);
    
    // Cabeçalhos de segurança exigidos pela arquitetura
    http.addHeader("Content-Type", "application/json");
    http.addHeader("device-id", deviceId);
    http.addHeader("hash", deviceHash);
    
    // Payload JSON com o dado bruto
    String payload = "{\"distance_cm\": " + String(distance_cm) + "}";
    int httpResponseCode = http.POST(payload);
    
    Serial.print("HTTP Response: ");
    Serial.println(httpResponseCode);
    http.end();
  }
  
  // Pausa de 10 segundos para visualização no simulador
  delay(10000); 
}