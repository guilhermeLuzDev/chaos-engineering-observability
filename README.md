# Seminário de Observabilidade: Chaos Engineering com Circuit Breaker

Este repositório contém a demonstração prática completa para o **Tema 7: Chaos Engineering com Observabilidade**, construída para rodar com um único comando via **Docker Compose**.

---

## 🎯 Objetivo da Demonstração

Provar experimentalmente a eficácia do padrão de resiliência **Circuit Breaker** frente a uma degradação severa de rede em uma dependência crítica, diagnosticando o comportamento do sistema em tempo real por meio de **métricas RED** (Rate, Errors, Duration) coletadas pelo **Prometheus** e visualizadas no **Grafana**.

---

## 🏗️ Arquitetura da Solução

```text
       [ Gerador de Carga ] (~4 req/s constantes)
               │
               ▼
       ┌──────────────┐          ┌───────────┐          ┌──────────────┐
       │  Serviço de  │ ───────> │ Toxiproxy │ ───────> │  Serviço de  │
       │   Pedidos    │ <─────── │ (Proxy)   │ <─────── │  Pagamentos  │
       │ (FastAPI:8000)│         │  (:8475)  │          │ (FastAPI:8001)│
       └──────┬───────┘          └─────▲─────┘          └──────────────┘
              │                        │
       /metrics a cada 2s              │ (Injeção de Caos: python / curl)
              ▼                        │
       ┌──────────────┐                │
       │  Prometheus  │                │
       │   (:9090)    │                │
       └──────┬───────┘                │
              │                        │
              ▼                        │
       ┌──────────────┐                │
       │   Grafana    │ ───────────────┘
       │   (:3000)    │ (Dashboard RED + Circuit Breaker em tempo real)
       └──────────────┘
```

### Componentes:
1. **`order-service` (Porta 8000):** Microsserviço de criação de pedidos com implementação didática de **Circuit Breaker** (estados: *CLOSED*, *OPEN*, *HALF-OPEN*), timeout rígido de 1.0s e contingência (*fallback* gracioso).
2. **`payment-service` (Porta 8001):** API mock de processamento financeiro com latência normal de ~40ms.
3. **`toxiproxy` (Portas 8474 / 8475):** Proxy de injeção de caos criado pelo Shopify. O `order-service` se comunica com o `payment-service` passando exclusivamente pela porta `8475` do Toxiproxy.
4. **`load-generator`:** Envia tráfego contínuo (~4 requisições/s) para manter os gráficos vivos.
5. **`prometheus` (Porta 9090):** Raspa as métricas da aplicação a cada 2 segundos.
6. **`grafana` (Porta 3000):** Painel pré-configurado sem necessidade de login.

---

## 🚀 Como Executar (Comando Único)

### 1. Pré-requisitos
* Ter o **Docker** e o **Docker Compose** instalados e em execução.
* Python 3 instalado no computador (para rodar os scripts de caos).

### 2. Subir o ambiente
No terminal, dentro da pasta raiz do projeto, execute:

```bash
docker compose up --build
```

Aguarde cerca de 30 segundos até que todos os containers subam.

### 3. Acessar os painéis
* **Dashboard do Grafana:** [http://localhost:3000](http://localhost:3000)  
  *(Abre direto no dashboard do seminário, sem precisar de login nem senha!)*
* **Prometheus:** [http://localhost:9090](http://localhost:9090)
* **API de Pedidos:** [http://localhost:8000/docs](http://localhost:8000/docs)
* **Status do Circuit Breaker:** [http://localhost:8000/circuit-breaker/status](http://localhost:8000/circuit-breaker/status)

---

## 🎬 Roteiro da Demonstração ao Vivo (8 a 10 minutos)

Siga este roteiro durante a apresentação:

### Etapa 1: Estado Estável (Steady State) — 2 min
1. Abra o Grafana em [http://localhost:3000](http://localhost:3000).
2. **O que mostrar:**
   * Painel **Estado do Circuit Breaker:** verde (`CLOSED - Normal / Saudável`).
   * Painel **Throughput:** taxa de ~4 req/s com linha verde de 100% de sucesso.
   * Painel **Latência:** p50 e p99 abaixo de 60ms.
3. **O que falar:**  
   *"Nossa hipótese de estado estável: sob condições normais, o sistema atende o tráfego com latência p99 < 100ms e zero erros."*

---

### Etapa 2: O Experimento de Caos (Injeção de Falha) — 1 min
Em outro terminal, execute o script para injetar **3 segundos de latência** no gateway de pagamentos:

```bash
python chaos/inject_latency.py
```
*(Ou via curl: `curl -X POST http://localhost:8474/proxies/payment_proxy/toxics -d "{\"name\":\"payment_latency\",\"type\":\"latency\",\"toxicity\":1.0,\"attributes\":{\"latency\":3000}}"`)*

---

### Etapa 3: Detecção e Degradação — 2 min
1. Olhe para o Grafana.
2. **O que acontece:**
   * A latência p99 sobe imediatamente para **1.0 segundo** (que é o timeout configurado no `order-service`).
   * O gauge de **Falhas Consecutivas** sobe: `1... 2... 3`.
3. **O que falar:**  
   *"O gateway de pagamento ficou extremamente lento. O serviço de pedidos tenta esperar até o limite do timeout (1s). Sem observabilidade, não saberíamos se o sistema caiu ou se está travado esperando respostas."*

---

### Etapa 4: Resiliência em Ação (Circuit Breaker Aberto) — 3 min
1. Após 3 falhas consecutivas:
   * O painel **Estado do Circuit Breaker** muda para **VERMELHO (`OPEN - Fail-Fast`)**!
   * A linha de **Throughput** passa de verde para laranja (*Fallback Acionado*).
   * A **Latência p99 despenca** de 1.000ms de volta para **~10ms**!
2. **O que falar:**  
   *"Observem o poder do Circuit Breaker: para não esgotar as conexões e threads do servidor, ele 'desarmou'. Ele interrompeu as chamadas à rede e passou a responder imediatamente via Fallback gracioso (salvando o pedido em contingência offline). O usuário não fica esperando numa tela travada."*

---

### Etapa 5: Autocura (Restaurando a Normalidade) — 2 min
Remova o caos executando:

```bash
python chaos/reset_chaos.py
```

1. **O que acontece:**
   * O Circuit Breaker aguarda o tempo de recuperação (8 segundos) e muda para **AMARELO (`HALF-OPEN`)**.
   * Ele envia uma requisição piloto. Como o pagamento respondeu rápido, ele muda para **VERDE (`CLOSED`)**.
   * O throughput volta a ser 100% verde (Sucesso).
2. **O que falar:**  
   *"O sistema detectou a cura da dependência sozinho, fechou o circuito e restabeleceu a operação normal sem qualquer intervenção manual."*

---

## 📊 Sinais e Métricas Coletadas

| Métrica no Prometheus | Tipo | Significado Operacional |
| :--- | :--- | :--- |
| `circuit_breaker_state` | Gauge | Estado do disjuntor (0: Closed, 1: Open, 2: Half-Open) |
| `circuit_breaker_failures_count` | Gauge | Quantidade de falhas consecutivas antes de desarmar |
| `order_requests_total` | Counter | Total de requisições rotuladas por status (`success`, `fallback`) |
| `order_request_duration_seconds` | Histogram | Latência para cálculo de percentis (p50, p95, p99) |

---

## 🛑 Como Parar o Ambiente

Para encerrar e limpar os containers:

```bash
docker compose down
```
