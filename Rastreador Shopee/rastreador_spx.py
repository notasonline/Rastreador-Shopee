"""
Rastreador SPX Brasil → Telegram (CallMeBot)
=============================================
Faz scraping do site oficial spx.com.br, captura TODOS os eventos
detalhados de rastreamento e envia no Telegram via CallMeBot
quando qualquer status novo aparecer.

DEPENDÊNCIAS:
    pip install selenium webdriver-manager requests

CONFIGURAÇÃO:
    1. Confirme seu @username do Telegram na variável TELEGRAM_USER
    2. Para rodar localmente: python rastreador_spx.py
    3. Para rodar na nuvem: veja seção DEPLOY RAILWAY no final
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

TRACKING_NUMBER = os.environ.get("TRACKING_NUMBER", "BR263350626670N")

# Seu @username do Telegram
TELEGRAM_USER   = os.environ.get("TELEGRAM_USER", "@Yuhkimentor")

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

        wait = WebDriverWait(driver, 20)

        # Tenta diferentes seletores que o SPX BR pode usar
        possiveis_seletores = [
            "[class*='tracking-event']",
            "[class*='timeline']",
            "[class*='track-item']",
            "[class*='shipment']",
            "li[class*='event']",
            "div[class*='status']",
        ]

        for seletor in possiveis_seletores:
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, seletor)))
                break
            except Exception:
                continue

        time.sleep(3)  # aguarda renderização completa

        itens = driver.find_elements(By.CSS_SELECTOR,
            "[class*='track'], [class*='timeline'], [class*='event'], "
            "[class*='status-item'], li"
        )

        for item in itens:
            texto = item.text.strip()
            if len(texto) > 10:
                eventos.append({
                    "texto": texto,
                    "html_class": item.get_attribute("class") or ""
                })

        # Fallback: captura texto geral da página
        if not eventos:
            print("⚠️  Seletores específicos não funcionaram. Capturando texto geral...")
            body = driver.find_element(By.TAG_NAME, "body")
            linhas = [l.strip() for l in body.text.split("\n") if len(l.strip()) > 15]
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
        json.dump(
            {"eventos_vistos": eventos_vistos,
             "ultima_consulta": datetime.now().isoformat()},
            f, ensure_ascii=False, indent=2
        )


def enviar_telegram(novos_textos):
    """Envia mensagem via CallMeBot para o Telegram."""
    total = len(novos_textos)
    linhas = "\n\n".join(f"▸ {t}" for t in novos_textos)
    mensagem = (
        f"📦 SPX — {TRACKING_NUMBER}\n"
        f"{total} nova(s) atualizacao(oes):\n\n"
        f"{linhas}\n\n"
        f"Verificado: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )

    # Endpoint CallMeBot para Telegram
    url = (
        f"https://api.callmebot.com/text.php"
        f"?user={TELEGRAM_USER}"
        f"&text={quote(mensagem)}"
    )

    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            print(f"✅ Telegram enviado! ({total} evento(s) novo(s))")
        else:
            print(f"⚠️  CallMeBot status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"❌ Erro ao enviar Telegram: {e}")


def main():
    print(f"\n🔍 Rastreando: {TRACKING_NUMBER}")
    print(f"   {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")

    eventos_atuais = buscar_eventos()
    if not eventos_atuais:
        print("⚠️  Nenhum evento encontrado. O site pode estar fora do ar ou bloqueando.")
        return

    print(f"📋 {len(eventos_atuais)} elemento(s) capturado(s) do site.")

    historico = carregar_ultimo_status()
    vistos = set(historico.get("eventos_vistos", []))

    novos = [e["texto"] for e in eventos_atuais if e["texto"] not in vistos]

    if novos:
        print(f"\n🆕 {len(novos)} evento(s) novo(s):")
        for n in novos:
            print(f"   → {n[:100]}")
        enviar_telegram(novos)
        todos_vistos = list(vistos | {e["texto"] for e in eventos_atuais})
        salvar_status(todos_vistos)
    else:
        print("✔️  Nenhuma atualização nova.")
        salvar_status(list(vistos))


if __name__ == "__main__":
    main()


# ============================================================
#  DEPLOY NO RAILWAY (grátis)
# ============================================================
#
#  Estrutura de arquivos:
#
#    meu-rastreador/
#    ├── rastreador_spx.py   ← este arquivo
#    ├── requirements.txt
#    ├── Procfile
#    └── nixpacks.toml
#
#  Passos:
#    1. Crie conta em railway.app
#    2. New Project → Deploy from GitHub repo
#    3. Em "Variables" adicione:
#         TRACKING_NUMBER = BR263350626670N
#         TELEGRAM_USER   = @Yuhkimentor
#    4. Em "Settings → Cron Schedule":
#         0 * * * *    (roda todo início de hora)
#    5. Deploy! 🚀
#
# ============================================================
