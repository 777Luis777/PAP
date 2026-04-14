try:
    import webview
except ImportError:
    raise RuntimeError("pywebview is not installed. Install it with 'pip install pywebview'.")

import subprocess
import threading
import os
import sys
import time

def start_django():
    # Start the Django development server on port 8080 using absolute paths
    base_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(base_dir, "Backend")
    manage_py = os.path.join(backend_dir, "manage.py")
    subprocess.Popen([sys.executable, manage_py, "runserver", "8080"], cwd=backend_dir)

if __name__ == "__main__":
    # Arranca o Django num thread
    threading.Thread(target=start_django, daemon=True).start()

    # Caminho absoluto do ícone
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(BASE_DIR, "img", "icone1.png")

    # Criar e iniciar janela desktop
    window = webview.create_window("FaceTrack","http://127.0.0.1:8080",resizable=True,maximized=True)
    webview.start(icon=icon_path)