"""
Rastreador SPX Brasil → WhatsApp
=================================
Faz scraping do site oficial spx.com.br, captura TODOS os eventos
detalhados de rastreamento e envia no WhatsApp via CallMeBot
quando qualquer status novo aparecer.

DEPENDÊNCIAS:
    pip install selenium selenium-wire webdriver-manager requests

CONFIGURAÇÃO:
    1. Preencha as variáveis CONFIG abaixo
    2. Ative o CallMeBot no WhatsApp (veja instruções no final)
    3. Para rodar localmente: python rastreador_spx.py
    4. Para rodar na nuvem: veja seção DEPLOY RAILWAY no final
"""

import json
import os
import time
import requests
from datetime import datetime
from urllib.parse import quote

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ============================================================
#  CONFIG — preencha aqui (ou use variáveis de ambiente)
# ============================================================

TRACKING_NUMBER  = os.environ.get("TRACKING_NUMBER",  "BR263350626670N")
WHATSAPP_NUMERO  = os.environ.get("WHATSAPP_NUMERO",  "")   # ex: 5583999990000
WHATSAPP_API_KEY = os.environ.get("WHATSAPP_API_KEY", "")   # chave CallMeBot

ARQUIVO_STATUS   = "/tmp/ultimo_status_spx.json"
URL_RASTREAMENTO = f"https://spx.com.br/rastreamento?code={TRACKING_NUMBER}"

# ============================================================


def criar_driver():
    """Cria o Chrome headless (sem interface gráfica)."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,900")
    options.add_argument(
        "user-agent=Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def buscar_eventos():
    """
    Abre o site da SPX, aguarda os eventos carregarem e retorna
    uma lista de dicionários com os detalhes de cada evento.
    """
    driver = criar_driver()
    eventos = []

    try:
        print(f"🌐 Acessando: {URL_RASTREAMENTO}")
        driver.get(URL_RASTREAMENTO)

        # Aguarda até 20s pelos eventos aparecerem na página
        wait = WebDriverWait(driver, 20)

        # O site SPX renderiza os eventos em uma lista — aguardamos qualquer
        # elemento que contenha texto de rastreamento aparecer
        # Seletores comuns usados pelo SPX BR (ajuste se necessário):
        possiveis_seletores = [
            "[class*='tracking-event']",
            "[class*='timeline']",
            "[class*='track-item']",
            "[class*='shipment']",
            "li[class*='event']",
            "div[class*='status']",
        ]

        container = None
        for seletor in possiveis_seletores:
            try:
                container = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, seletor))
                )
                if container:
                    break
            except Exception:
                continue

        # Aguarda um pouco mais para a lista completa renderizar
        time.sleep(3)

        # Captura o HTML completo da área de rastreamento para debug
        page_source = driver.page_source

        # Tenta extrair os eventos de diferentes estruturas HTML possíveis
        itens = driver.find_elements(By.CSS_SELECTOR,
            "[class*='track'], [class*='timeline'], [class*='event'], "
            "[class*='status-item'], li"
        )

        for item in itens:
            texto = item.text.strip()
            if len(texto) > 10:  # ignora elementos vazios ou muito curtos
                eventos.append({
                    "texto": texto,
                    "html_class": item.get_attribute("class") or ""
                })

        # Se não achou nada estruturado, pega o texto da página toda
        if not eventos:
            print("⚠️  Nenhum seletor específico funcionou. Capturando texto geral...")
            body = driver.find_element(By.TAG_NAME, "body")
            texto_pagina = body.text
            # Quebra em linhas não-vazias como fallback
            linhas = [l.strip() for l in texto_pagina.split("\n") if len(l.strip()) > 15]
            eventos = [{"texto": l, "html_class": "fallback"} for l in linhas]

    except Exception as e:
        print(f"❌ Erro no scraping: {e}")
    finally:
        driver.quit()

    return eventos


def carregar_ultimo_status():
    if os.path.exists(ARQUIVO_STATUS):
        with open(ARQUIVO_STATUS, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"eventos_vistos": []}


def salvar_status(eventos_vistos):
    with open(ARQUIVO_STATUS, "w", encoding="utf-8") as f:
        json.dump({"eventos_vistos": eventos_vistos,
                   "ultima_consulta": datetime.now().isoformat()},
                  f, ensure_ascii=False, indent=2)


def enviar_whatsapp(novos_textos):
    total = len(novos_textos)
    linhas = "\n\n".join(f"▸ {t}" for t in novos_textos)
    mensagem = (
        f"📦 *SPX — {TRACKING_NUMBER}*\n"
        f"{total} nova(s) atualização(ões):\n\n"
        f"{linhas}\n\n"
        f"🕑 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )

    url = (
        f"https://api.callmebot.com/whatsapp.php"
        f"?phone={WHATSAPP_NUMERO}"
        f"&text={quote(mensagem)}"
        f"&apikey={WHATSAPP_API_KEY}"
    )

    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            print(f"✅ WhatsApp enviado! ({total} evento(s) novo(s))")
        else:
            print(f"⚠️  CallMeBot status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"❌ Erro ao enviar WhatsApp: {e}")


def main():
    print(f"\n🔍 Rastreando: {TRACKING_NUMBER}")
    print(f"   {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")

    eventos_atuais = buscar_eventos()
    if not eventos_atuais:
        print("⚠️  Nenhum evento encontrado. O site pode estar bloqueando ou fora do ar.")
        return

    print(f"📋 {len(eventos_atuais)} elemento(s) capturado(s) do site.")

    historico = carregar_ultimo_status()
    vistos = set(historico.get("eventos_vistos", []))

    novos = [e["texto"] for e in eventos_atuais if e["texto"] not in vistos]

    if novos:
        print(f"\n🆕 {len(novos)} evento(s) novo(s):")
        for n in novos:
            print(f"   → {n[:100]}")
        enviar_whatsapp(novos)
        todos_vistos = list(vistos | set(e["texto"] for e in eventos_atuais))
        salvar_status(todos_vistos)
    else:
        print("✔️  Nenhuma atualização nova.")
        salvar_status(list(vistos))


if __name__ == "__main__":
    main()


# ============================================================
#  ATIVAR CALLMEBOT NO WHATSAPP (faça isso 1 única vez)
# ============================================================
#
#  1. Adicione o número +34 644 98 44 69 na sua agenda
#  2. Mande a mensagem via WhatsApp:
#        I allow callmebot to send me messages
#  3. Você receberá sua apikey em segundos
#  4. Cole o número e a apikey nas variáveis WHATSAPP_*
#
# ============================================================
#  DEPLOY NO RAILWAY (grátis)
# ============================================================
#
#  Estrutura de arquivos necessária:
#
#    meu-rastreador/
#    ├── rastreador_spx.py       ← este arquivo
#    ├── requirements.txt        ← veja abaixo
#    ├── Procfile                ← veja abaixo
#    └── nixpacks.toml           ← veja abaixo
#
#  requirements.txt:
#    selenium
#    webdriver-manager
#    requests
#
#  Procfile:
#    worker: python rastreador_spx.py
#
#  nixpacks.toml (instala o Chrome no Railway):
#    [phases.setup]
#    nixPkgs = ["chromium", "chromedriver"]
#
#  Passos no Railway:
#    1. Crie conta em railway.app (gratuito)
#    2. "New Project" → "Deploy from GitHub repo"
#    3. Faça upload dos arquivos acima num repositório GitHub
#    4. No Railway, vá em "Variables" e adicione:
#         TRACKING_NUMBER  = BR263350626670N
#         WHATSAPP_NUMERO  = 55XXXXXXXXXXX
#         WHATSAPP_API_KEY = sua_chave_callmebot
#    5. Vá em "Settings" → "Cron Schedule" → coloque:
#         0 * * * *    (roda todo início de hora)
#    6. Deploy! 🚀
#
# ============================================================
