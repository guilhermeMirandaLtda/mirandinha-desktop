"""
Ponto de entrada principal da aplicação desktop Mirandinha.
Inicializa o motor pywebview e vincula a interface Mofi + Mirandinha.
"""
import os
import sys
import webview
from core.bridge import MirandinhaBridge

def main():
    # Caminho absoluto da pasta da interface web
    base_dir = os.path.dirname(os.path.abspath(__file__))
    web_dir = os.path.join(base_dir, "web")
    index_html = os.path.join(web_dir, "index.html")

    if not os.path.exists(index_html):
        print(f"Erro: Arquivo {index_html} não encontrado!")
        sys.exit(1)

    bridge = MirandinhaBridge()

    # Criação da janela desktop nativa
    window = webview.create_window(
        title="Mirandinha — RPA & Análises Avançadas",
        url=index_html,
        js_api=bridge,
        width=1280,
        height=820,
        min_size=(1024, 700),
        background_color="#F4F6F9"
    )

    bridge.set_window(window)

    def on_closing():
        """Intercepta o clique no 'X' da janela e checa se há automação ativa."""
        status_res = bridge.is_rpa_running()
        is_running = status_res.get("data", {}).get("is_running", False)
        if is_running:
            # Invoca o SweetAlert2 no frontend e impede o fechamento imediato
            window.evaluate_js("window.appBridge.confirmExitApp();")
            return False
        return True

    window.events.closing += on_closing

    # Inicia o loop de eventos pywebview
    webview.start(debug=False)

if __name__ == "__main__":
    main()

