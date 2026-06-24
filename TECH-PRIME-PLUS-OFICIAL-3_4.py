import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, timedelta
import sqlite3
import os
import shutil
import webbrowser
from tkcalendar import DateEntry
import pandas as pd
from fpdf import FPDF
from dateutil.relativedelta import relativedelta
import urllib.parse
import hashlib
import subprocess
import threading
import json
try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False
try:
    from http.server import HTTPServer, BaseHTTPRequestHandler
    WEBHOOK_OK = True
except ImportError:
    WEBHOOK_OK = False

SALT_CHAVE = "TECH_PRIME_SECRET_2026"
_DB_CONFIG_FILE = "db_config.txt"

# ── Atualização Automática via GitHub ────────────────────────────────────────
VERSAO_ATUAL = "3.4"
GITHUB_REPO_OWNER = "techprimedev-br"
GITHUB_REPO_NAME = "TechPrimeGestao"
GITHUB_REPO = f"{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}"
ARQUIVO_PRINCIPAL = "TECH-PRIME-PLUS-OFICIAL-3_4.py"
_UPDATE_CONFIG_FILE = "update_config.json"

def _carregar_config_update():
    try:
        with open(_UPDATE_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"auto_check": True}

def _salvar_config_update(cfg):
    with open(_UPDATE_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

def verificar_atualizacao_github(callback_resultado=None):
    """Verifica se existe nova versão no GitHub Releases.
    callback_resultado(tem_update, info_dict) é chamado na thread principal."""
    if not REQUESTS_OK:
        if callback_resultado:
            callback_resultado(False, {"erro": "Módulo 'requests' não instalado."})
        return

    def _check():
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            r = requests.get(url, timeout=10)
            if r.status_code == 404:
                url_tags = f"https://api.github.com/repos/{GITHUB_REPO}/tags"
                r2 = requests.get(url_tags, timeout=10)
                if r2.status_code == 200 and r2.json():
                    tag = r2.json()[0]
                    tag_name = tag["name"].lstrip("vV")
                    if _versao_mais_nova(tag_name, VERSAO_ATUAL):
                        info = {
                            "versao_nova": tag_name,
                            "versao_atual": VERSAO_ATUAL,
                            "tag": tag["name"],
                            "download_url": f"https://raw.githubusercontent.com/{GITHUB_REPO}/{tag['name']}/{ARQUIVO_PRINCIPAL}",
                            "notas": f"Nova versão {tag_name} disponível.",
                            "fonte": "tag"
                        }
                        if callback_resultado:
                            callback_resultado(True, info)
                        return
                if callback_resultado:
                    callback_resultado(False, {"versao_atual": VERSAO_ATUAL, "msg": "Nenhuma release encontrada."})
                return

            if r.status_code != 200:
                if callback_resultado:
                    callback_resultado(False, {"erro": f"Erro HTTP {r.status_code}"})
                return

            data = r.json()
            tag_name = data.get("tag_name", "").lstrip("vV")

            if not _versao_mais_nova(tag_name, VERSAO_ATUAL):
                if callback_resultado:
                    callback_resultado(False, {
                        "versao_atual": VERSAO_ATUAL,
                        "versao_remota": tag_name,
                        "msg": "Você já está na versão mais recente."
                    })
                return

            download_url = None
            for asset in data.get("assets", []):
                if asset["name"].endswith(".py"):
                    download_url = asset["browser_download_url"]
                    break
            if not download_url:
                download_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{data.get('tag_name', 'main')}/{ARQUIVO_PRINCIPAL}"

            info = {
                "versao_nova": tag_name,
                "versao_atual": VERSAO_ATUAL,
                "tag": data.get("tag_name", ""),
                "download_url": download_url,
                "notas": data.get("body", "Sem notas de atualização."),
                "fonte": "release"
            }
            if callback_resultado:
                callback_resultado(True, info)
        except Exception as e:
            if callback_resultado:
                callback_resultado(False, {"erro": str(e)})

    threading.Thread(target=_check, daemon=True).start()

def _versao_mais_nova(remota, local):
    """Compara versões no formato X.Y.Z — retorna True se remota > local."""
    try:
        def parse_v(v):
            return [int(x) for x in v.replace("-", ".").split(".")]
        return parse_v(remota) > parse_v(local)
    except:
        return remota != local

def baixar_e_aplicar_atualizacao(download_url, callback_progresso=None):
    """Baixa o arquivo atualizado e substitui o script atual.
    callback_progresso(etapa, msg) é chamado para atualizar a UI."""
    def _download():
        try:
            if callback_progresso:
                callback_progresso("baixando", "Baixando atualização...")

            r = requests.get(download_url, timeout=60, stream=True)
            if r.status_code != 200:
                if callback_progresso:
                    callback_progresso("erro", f"Erro ao baixar: HTTP {r.status_code}")
                return False

            conteudo = r.content

            if callback_progresso:
                callback_progresso("salvando", "Criando backup e aplicando...")

            script_atual = os.path.abspath(__file__)
            pasta = os.path.dirname(script_atual) or "."

            backup_path = os.path.join(pasta, f"backup_v{VERSAO_ATUAL}_{ARQUIVO_PRINCIPAL}")
            try:
                shutil.copy2(script_atual, backup_path)
            except:
                pass

            temp_path = script_atual + ".update_tmp"
            with open(temp_path, "wb") as f:
                f.write(conteudo)

            try:
                compile(conteudo.decode("utf-8"), temp_path, "exec")
            except SyntaxError as e:
                os.remove(temp_path)
                if callback_progresso:
                    callback_progresso("erro", f"Arquivo baixado contém erro de sintaxe:\n{e}")
                return False

            os.replace(temp_path, script_atual)

            if callback_progresso:
                callback_progresso("concluido", "Atualização aplicada com sucesso!\nReinicie o sistema para usar a nova versão.")
            return True

        except Exception as e:
            if callback_progresso:
                callback_progresso("erro", f"Falha na atualização:\n{e}")
            return False

    threading.Thread(target=_download, daemon=True).start()

def _resolver_db_file():
    """Se db_config.txt existir e apontar para caminho de rede válido, usa esse banco.
    Caso contrário usa o banco local."""
    if os.path.exists(_DB_CONFIG_FILE):
        try:
            caminho = open(_DB_CONFIG_FILE, encoding="utf-8").read().strip()
            if caminho and os.path.exists(os.path.dirname(caminho) or "."):
                return caminho
        except: pass
    return "tech_prime_plus.db"

DB_FILE = _resolver_db_file()


def hash_senha(senha):
    return hashlib.sha256(senha.encode()).hexdigest()

# ── Sistema de Perfis e Permissões ────────────────────────────────────────────
PERMISSOES_DISPONIVEIS = {
    "painel":       "Painel Principal (dashboard)",
    "clientes":     "Aba Clientes (cadastro/edição)",
    "multiacesso":  "Multiacesso (painéis)",
    "custos":       "Controle de Custos",
    "logs":         "Logs do Sistema",
    "configuracoes":"Configurações",
    "excluir":      "Excluir Clientes",
    "renovar":      "Renovar Clientes",
    "whatsapp":     "Enviar WhatsApp",
    "exportar":     "Exportar PDF/Excel",
    "backup":       "Backup/Restauração",
    "importar":     "Importar Clientes",
}

PERFIS_PREDEFINIDOS = {
    "basico": {
        "label": "Básico",
        "descricao": "Acesso somente ao dashboard e visualização de clientes",
        "permissoes": ["painel", "clientes"],
    },
    "operador": {
        "label": "Operador",
        "descricao": "Acesso operacional: clientes, renovação e WhatsApp",
        "permissoes": ["painel", "clientes", "renovar", "whatsapp", "multiacesso"],
    },
    "completo": {
        "label": "Completo",
        "descricao": "Acesso total ao sistema",
        "permissoes": list(PERMISSOES_DISPONIVEIS.keys()),
    },
    "personalizado": {
        "label": "Personalizado",
        "descricao": "Permissões escolhidas manualmente",
        "permissoes": [],
    },
}

def get_permissoes_usuario(db_file, usuario):
    """Retorna set de permissões do usuário. Admin/master tem tudo."""
    try:
        import sqlite3 as _sq
        conn = _sq.connect(db_file)
        row = conn.execute(
            "SELECT perfil, COALESCE(permissoes,'') FROM usuarios_sistema WHERE usuario=?",
            (usuario,)
        ).fetchone()
        conn.close()
        if not row:
            return set(PERMISSOES_DISPONIVEIS.keys())  # fallback: tudo
        perfil, permissoes_json = row
        if perfil == "completo":
            return set(PERMISSOES_DISPONIVEIS.keys())
        if perfil in PERFIS_PREDEFINIDOS and perfil != "personalizado":
            return set(PERFIS_PREDEFINIDOS[perfil]["permissoes"])
        # personalizado
        try:
            import json as _json
            perms = _json.loads(permissoes_json) if permissoes_json else []
            return set(perms)
        except:
            return set(PERMISSOES_DISPONIVEIS.keys())
    except:
        return set(PERMISSOES_DISPONIVEIS.keys())

def _senha_master():
    """Senha master muda todo dia: AAAAMMDD + TechPrime.
    Ex: 20260513TechPrime  — nunca fica gravada no banco."""
    from datetime import datetime
    d = datetime.now()
    return f"{d.year}{d.month:02d}{d.day:02d}TechPrime"

def verificar_login(usuario, senha):
    """Autentica usuario normal OU master (usuario 'admin', senha dinâmica)."""
    # ── Master oculto ──
    if usuario.lower() == "admin" and senha == _senha_master():
        return True
    import sqlite3 as _sq
    try:
        conn = _sq.connect(DB_FILE)
        row = conn.execute("SELECT senha_hash FROM usuarios_sistema WHERE usuario=?",
                           (usuario,)).fetchone()
        conn.close()
        return row and row[0] == hash_senha(senha)
    except: return False

def inicializar_banco_global():
    """Cria as tabelas necessárias antes mesmo do login."""
    import sqlite3 as _sq
    conn = _sq.connect(DB_FILE)
    conn.execute('''CREATE TABLE IF NOT EXISTS usuarios_sistema
                   (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario TEXT UNIQUE,
                    senha_hash TEXT,
                    email TEXT NOT NULL DEFAULT \'\')'''
    )
    conn.execute('''CREATE TABLE IF NOT EXISTS logs
                   (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tipo TEXT, descricao TEXT, data TEXT)''')
    try:
        conn.execute("ALTER TABLE logs ADD COLUMN usuario TEXT DEFAULT ''")
    except: pass
    try:
        conn.execute('ALTER TABLE usuarios_sistema ADD COLUMN email TEXT NOT NULL DEFAULT \'\'')
    except: pass
    try:
        conn.execute("ALTER TABLE usuarios_sistema ADD COLUMN perfil TEXT NOT NULL DEFAULT 'completo'")
    except: pass
    try:
        conn.execute("ALTER TABLE usuarios_sistema ADD COLUMN permissoes TEXT NOT NULL DEFAULT ''")
    except: pass
    conn.commit(); conn.close()

def primeiro_acesso():
    import sqlite3 as _sq
    try:
        conn = _sq.connect(DB_FILE)
        count = conn.execute("SELECT COUNT(*) FROM usuarios_sistema").fetchone()[0]
        conn.close()
        return count == 0
    except: return True


_hwid_cache = None

def get_hwid():
    """HWID robusto: serial da placa-mãe + UUID do Windows combinados."""
    global _hwid_cache
    if _hwid_cache:
        return _hwid_cache
    partes = []
    # 1. Serial da placa-mãe
    try:
        r = subprocess.check_output("wmic baseboard get serialnumber",
                                    shell=True, timeout=3).decode(errors="ignore")
        serial = [l.strip() for l in r.splitlines() if l.strip() and "SerialNumber" not in l]
        if serial and serial[0] not in ("", "None", "To be filled by O.E.M.", "Default string"):
            partes.append(serial[0])
    except: pass
    # 2. UUID da máquina Windows
    try:
        r = subprocess.check_output("wmic csproduct get uuid",
                                    shell=True, timeout=3).decode(errors="ignore")
        uuid = [l.strip() for l in r.splitlines() if l.strip() and "UUID" not in l]
        if uuid and uuid[0] not in ("", "FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF"):
            partes.append(uuid[0])
    except: pass
    # 3. Fallback: hostname + username (menos seguro mas nunca vazio)
    if not partes:
        import socket, getpass
        partes.append(socket.gethostname() + getpass.getuser())
    raw = "|".join(partes)
    _hwid_cache = hashlib.sha256(raw.encode()).hexdigest()[:24].upper()
    return _hwid_cache

def gerar_chave_para_hwid(hwid):
    """Gera a chave de ativação para um HWID específico."""
    return hashlib.sha256((hwid + SALT_CHAVE).encode()).hexdigest()[:16].upper()

def validar_licenca(chave_inserida):
    hwid = get_hwid()
    return chave_inserida == gerar_chave_para_hwid(hwid)

def ler_licenca_arquivo():
    """Lê e valida o license.dat. Retorna True só se HWID bater com a máquina atual."""
    if not os.path.exists("license.dat"):
        return False
    try:
        with open("license.dat", "r") as f:
            conteudo = f.read().strip()
        # Formato: HWID_GRAVADO|CHAVE|ASSINATURA
        partes = conteudo.split("|")
        if len(partes) != 3:
            return False
        hwid_gravado, chave_gravada, assinatura = partes
        # 1. HWID do arquivo deve bater com o da máquina atual
        if hwid_gravado != get_hwid():
            return False
        # 2. Chave deve ser válida para esse HWID
        if chave_gravada != gerar_chave_para_hwid(hwid_gravado):
            return False
        # 3. Assinatura do arquivo (anti-adulteração)
        assinatura_esperada = hashlib.sha256(
            (hwid_gravado + chave_gravada + SALT_CHAVE).encode()
        ).hexdigest()[:16].upper()
        return assinatura == assinatura_esperada
    except:
        return False

def salvar_licenca_arquivo(chave):
    """Salva license.dat com HWID + chave + assinatura."""
    hwid = get_hwid()
    assinatura = hashlib.sha256(
        (hwid + chave + SALT_CHAVE).encode()
    ).hexdigest()[:16].upper()
    with open("license.dat", "w") as f:
        f.write(f"{hwid}|{chave}|{assinatura}")

def enviar_licenca_por_email(email_cliente, nome_cliente=""):
    """Gera a chave para o HWID atual e envia por e-mail para o cliente."""
    hwid   = get_hwid()
    chave  = gerar_chave_para_hwid(hwid)
    nome   = nome_cliente or email_cliente.split("@")[0]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "🔑 Sua Chave de Ativação — TECH PRIME PLUS"
    msg["From"]    = _SMTP_FROM
    msg["To"]      = email_cliente

    corpo_html = f"""
    <html><body style="font-family:Arial,sans-serif;background:#f0f0f0;padding:20px">
      <div style="max-width:500px;margin:auto;background:white;border-radius:8px;overflow:hidden">
        <div style="background:#1a3a6c;padding:20px;text-align:center">
          <h2 style="color:white;margin:0">TECH PRIME PLUS</h2>
          <p style="color:#aad4f5;margin:4px 0">Ativação do Sistema</p>
        </div>
        <div style="padding:24px">
          <p>Olá <strong>{nome}</strong>,</p>
          <p>Sua licença foi gerada com sucesso! Utilize a chave abaixo para ativar o sistema:</p>
          <div style="background:#f0f4ff;border:2px solid #1a3a6c;border-radius:6px;
                      padding:16px;text-align:center;font-size:26px;font-weight:bold;
                      letter-spacing:4px;color:#1a3a6c;margin:16px 0">
            {chave}
          </div>
          <p style="font-size:12px;color:#555">
            🔒 Esta chave é vinculada exclusivamente à sua máquina (ID: <code>{hwid}</code>)
            e não funcionará em outros computadores.
          </p>
          <p style="font-size:12px;color:#555">
            Para ativar: abra o sistema → cole a chave no campo de ativação → clique em ATIVAR.
          </p>
        </div>
        <div style="background:#f0f0f0;padding:10px;text-align:center;font-size:11px;color:#888">
          © 2026 TECH PRIME PLUS — Emerson Amorim
        </div>
      </div>
    </body></html>
    """
    msg.attach(MIMEText(corpo_html, "html", "utf-8"))
    try:
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=10) as srv:
            srv.ehlo(); srv.starttls()
            srv.login(_SMTP_USER, _SMTP_PASS)
            srv.sendmail(_SMTP_USER, email_cliente, msg.as_string())
        return True, chave
    except Exception as e:
        return False, str(e)



import smtplib
import random
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ── Credenciais fixas do e-mail do sistema ──
_SMTP_HOST   = "smtp.gmail.com"
_SMTP_PORT   = 587
_SMTP_USER   = "techprimeplus.noreply@gmail.com"
_SMTP_PASS   = "emjsilpifmicezak"          # senha de app (sem espaços)
_SMTP_FROM   = "TECH PRIME PLUS <techprimeplus.noreply@gmail.com>"

def gerar_senha_temporaria(tamanho=10):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=tamanho))

def enviar_email_recuperacao(email_destino, usuario, senha_temp):
    """Envia senha temporária usando o e-mail fixo do sistema."""
    msg = MIMEMultipart('alternative')
    msg['Subject'] = '🔑 Recuperação de Senha — TECH PRIME PLUS'
    msg['From']    = _SMTP_FROM
    msg['To']      = email_destino

    corpo_html = f"""
    <html><body style="font-family:Arial,sans-serif;background:#f0f0f0;padding:20px">
      <div style="max-width:480px;margin:auto;background:white;border-radius:8px;overflow:hidden">
        <div style="background:#1a3a6c;padding:20px;text-align:center">
          <h2 style="color:white;margin:0">TECH PRIME PLUS</h2>
          <p style="color:#aad4f5;margin:4px 0">Recuperação de Senha</p>
        </div>
        <div style="padding:24px">
          <p>Olá <strong>{usuario}</strong>,</p>
          <p>Recebemos uma solicitação de recuperação de senha para sua conta.</p>
          <p>Sua <strong>senha temporária</strong> é:</p>
          <div style="background:#f0f4ff;border:2px solid #1a3a6c;border-radius:6px;
                      padding:16px;text-align:center;font-size:22px;
                      font-weight:bold;letter-spacing:3px;color:#1a3a6c;margin:16px 0">
            {senha_temp}
          </div>
          <p>⚠ Use esta senha para entrar e <strong>altere-a imediatamente</strong> após o login.</p>
          <p style="color:#888;font-size:12px">Se você não solicitou isso, ignore este e-mail.</p>
        </div>
        <div style="background:#f0f0f0;padding:10px;text-align:center;font-size:11px;color:#888">
          © 2026 TECH PRIME PLUS — Emerson Amorim
        </div>
      </div>
    </body></html>
    """
    msg.attach(MIMEText(corpo_html, 'html', 'utf-8'))

    try:
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=10) as srv:
            srv.ehlo()
            srv.starttls()
            srv.login(_SMTP_USER, _SMTP_PASS)
            srv.sendmail(_SMTP_USER, email_destino, msg.as_string())
        return True, "E-mail enviado com sucesso!"
    except Exception as e:
        return False, f"Erro ao enviar e-mail: {e}"


class JanelaLicenca:
    def __init__(self, root_principal, callback_sucesso):
        self.window = tk.Toplevel(root_principal)
        self.window.title("Ativação - TECH PRIME PLUS")
        self.window.configure(bg="#1a3a6c")
        self.window.resizable(False, False)
        self.window.grab_set()
        self.callback = callback_sucesso
        self.hwid = get_hwid()
        self.window.update_idletasks()
        sw = self.window.winfo_screenwidth(); sh = self.window.winfo_screenheight()
        self.window.geometry(f"460x370+{(sw-460)//2}+{(sh-370)//2}")
        try: self.window.iconbitmap("logo.ico")
        except: pass

        # ── Cabeçalho ──
        tk.Label(self.window, text="TECH PRIME PLUS", font=("Arial", 16, "bold"),
                 bg="#1a3a6c", fg="white").pack(pady=(22, 2))
        tk.Label(self.window, text="Ativação do Sistema", font=("Arial", 9),
                 bg="#1a3a6c", fg="#aad4f5").pack(pady=(0, 14))

        frame = tk.Frame(self.window, bg="#f0f0f0", padx=30, pady=22)
        frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # ── Instrução ──
        tk.Label(frame,
                 text="Envie o ID abaixo para o suporte e informe que deseja ativar o sistema.",
                 bg="#f0f0f0", font=("Arial", 8, "italic"), fg="#555",
                 wraplength=380, justify="left").pack(anchor="w", pady=(0, 10))

        # ── ID da máquina ──
        tk.Label(frame, text="ID desta Máquina:", bg="#f0f0f0",
                 font=("Arial", 10, "bold")).pack(anchor="w")
        fr_id = tk.Frame(frame, bg="#f0f0f0")
        fr_id.pack(fill="x", pady=(4, 16))

        ent_id = tk.Entry(fr_id, font=("Arial", 11, "bold"), justify="center",
                          bd=0, bg="#e8eaf6", fg="#1a3a6c", relief="flat")
        ent_id.insert(0, self.hwid)
        ent_id.config(state="readonly")
        ent_id.pack(side=tk.LEFT, fill="x", expand=True, ipady=7)

        def copiar_id():
            self.window.clipboard_clear()
            self.window.clipboard_append(self.hwid)
            btn_copy.config(text="✅ Copiado!")
            self.window.after(1800, lambda: btn_copy.config(text="📋 Copiar"))

        btn_copy = tk.Button(fr_id, text="📋 Copiar", bg="#1a3a6c", fg="white",
                             font=("Arial", 9, "bold"), relief="flat", padx=10,
                             pady=7, cursor="hand2", command=copiar_id)
        btn_copy.pack(side=tk.LEFT, padx=(8, 0))

        # ── Separador ──
        ttk.Separator(frame, orient="horizontal").pack(fill="x", pady=(0, 16))

        # ── Campo da chave ──
        tk.Label(frame, text="Chave de Ativação:", bg="#f0f0f0",
                 font=("Arial", 10, "bold")).pack(anchor="w")
        fr_key = tk.Frame(frame, bg="#f0f0f0")
        fr_key.pack(fill="x", pady=(4, 0))

        self.ent_key = ttk.Entry(fr_key, font=("Arial", 12), justify="center")
        self.ent_key.pack(side=tk.LEFT, fill="x", expand=True, ipady=4)
        self.ent_key.focus()
        self.ent_key.bind("<Return>", lambda e: self.tentar_ativar())

        tk.Button(fr_key, text="✅ ATIVAR", bg="#1e5631", fg="white",
                  font=("Arial", 10, "bold"), relief="flat", padx=12, pady=6,
                  cursor="hand2", command=self.tentar_ativar).pack(side=tk.LEFT, padx=(8, 0))

        self.lbl_erro = tk.Label(frame, text="", bg="#f0f0f0", fg="#721c24",
                                  font=("Arial", 9, "bold"))
        self.lbl_erro.pack(pady=(10, 0))

        # ── Contato suporte ──
        tk.Label(frame,
                 text="Dúvidas? Entre em contato com o suporte para receber sua chave.",
                 bg="#f0f0f0", font=("Arial", 8, "italic"), fg="#888",
                 wraplength=380, justify="center").pack(pady=(8, 0))

    def tentar_ativar(self):
        chave = self.ent_key.get().strip().upper()
        if not chave:
            self.lbl_erro.config(text="Cole a chave de ativação recebida!"); return
        if validar_licenca(chave):
            salvar_licenca_arquivo(chave)
            messagebox.showinfo("✅ Ativado!", "Sistema ativado com sucesso!\nBem-vindo ao TECH PRIME PLUS.")
            self.window.destroy()
            self.callback()
        else:
            self.lbl_erro.config(text="❌ Chave inválida! Verifique e tente novamente.")
            self.ent_key.select_range(0, tk.END)


class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.widget.bind("<Enter>", self.show_tip)
        self.widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        if self.tip_window or not self.text: return
        x, y, _cx, cy = self.widget.bbox("insert")
        x = x + self.widget.winfo_rootx() + 25
        y = y + cy + self.widget.winfo_rooty() + 25
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(tw, text=self.text, background="#ffffe0", relief=tk.SOLID, borderwidth=1, font=("tahoma", "8"), padx=5, pady=2).pack()

    def hide_tip(self, event=None):
        tw = self.tip_window
        self.tip_window = None
        if tw: tw.destroy()

class TechPrimePlus:
    def __init__(self, root, usuario_logado="sistema"):
        self.root = root
        self.usuario_logado = usuario_logado
        # Carrega permissões do usuário logado
        self.permissoes = get_permissoes_usuario(DB_FILE, usuario_logado)
        self.root.title(f"TECH PRIME PLUS  v{VERSAO_ATUAL}")
        try:
            self.root.iconbitmap("logo.ico")
        except:
            pass  # Ícone não encontrado, continua sem ele
        self.root.state('zoomed')
        self.root.configure(bg="#f0f0f0")
        self.db_file = DB_FILE

        # ── Estilo do Treeview ──
        style = ttk.Style()
        style.configure("Treeview", font=("Arial", 9), rowheight=22)
        style.configure("Treeview.Heading", font=("Arial", 9))

        self.cores = {
            'total': '#1a3a6c', 'ativo': {'dark': '#1e5631', 'light': '#e7f3ec'},
            'alerta': {'dark': '#856404', 'light': '#fff3cd'}, 'vencido': {'dark': '#721c24', 'light': '#f8d7da'},
            'faturamento': '#0f172a'
        }

        self.col_order = ["N", "W", "U", "P", "PNL", "V", "D", "A", "S"]
        self.col_config = {
            "N":   {"text": "Nome",       "width": 140},
            "W":   {"text": "WhatsApp",   "width": 110},
            "U":   {"text": "Usuário",    "width": 100},
            "P":   {"text": "Senha",      "width": 100},
            "PNL": {"text": "Painel",     "width": 110},
            "V":   {"text": "Valor",      "width": 80},
            "D":   {"text": "Vencimento", "width": 95},
            "A":   {"text": "Adicionado", "width": 120},
            "S":   {"text": "Status",     "width": 75},
        }

        self.inicializar_banco()

        # ── Footer (criado ANTES do notebook para garantir espaço) ──
        self.footer = tk.Frame(self.root, bg="#1a3a6c", height=32)
        self.footer.pack(side=tk.BOTTOM, fill=tk.X, before=None)
        self.footer.pack_propagate(False)
        tk.Label(self.footer, text=f"© 2026 TECH PRIME PLUS v{VERSAO_ATUAL} - Emerson Amorim",
                 fg="white", bg="#1a3a6c", font=('Arial', 8, 'italic')).pack(side=tk.LEFT, pady=6, padx=10)
        tk.Button(self.footer, text="⏻ SAIR", bg="#721c24", fg="white", font=('Arial', 8, 'bold'),
                  relief="flat", padx=10, cursor="hand2",
                  command=lambda: self.root.quit() if messagebox.askyesno("Sair", "Deseja fechar o sistema?") else None
                  ).pack(side=tk.RIGHT, pady=4, padx=10)

        self.tab_control = ttk.Notebook(self.root)
        self.tab_gestao   = tk.Frame(self.tab_control, bg="#f0f0f0")
        self.tab_clientes = tk.Frame(self.tab_control, bg="#f0f0f0")
        self.tab_nav      = tk.Frame(self.tab_control, bg="white")
        self.tab_config   = tk.Frame(self.tab_control, bg="#f0f0f0")
        self.tab_custos   = tk.Frame(self.tab_control, bg="#f0f0f0")
        self.tab_logs     = tk.Frame(self.tab_control, bg="#f0f0f0")

        # Sempre adiciona Painel Principal
        self.tab_control.add(self.tab_gestao,   text=' Painel Principal ')
        # Demais abas só se tiver permissão
        if "clientes" in self.permissoes:
            self.tab_control.add(self.tab_clientes, text=' Clientes ')
        if "multiacesso" in self.permissoes:
            self.tab_control.add(self.tab_nav,      text=' Multiacesso ')
        if "custos" in self.permissoes:
            self.tab_control.add(self.tab_custos,   text=' Custos ')
        if "logs" in self.permissoes:
            self.tab_control.add(self.tab_logs,     text=' Logs ')
        if "configuracoes" in self.permissoes:
            self.tab_control.add(self.tab_config,   text=' Configurações ')
        self.tab_control.pack(expand=1, fill="both")

        # Controle de quais abas já foram construídas
        self._aba_construida = {
            'gestao': False, 'clientes': False, 'nav': False,
            'custos': False, 'logs': False, 'config': False
        }

        # Constrói só as abas essenciais agora
        self.criar_interface_gestao()
        self._aba_construida['gestao'] = True
        if "clientes" in self.permissoes:
            self.criar_interface_clientes()
            self._aba_construida['clientes'] = True

        # As demais abas são construídas na primeira vez que o usuário clicar
        self.tab_control.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self.atualizar_relogio()
        self.root.update_idletasks()
        self.root.update()
        self.atualizar_tudo()
        self.iniciar_atualizacao_automatica()
        self._verificar_update_startup()

    def _verificar_update_startup(self):
        """Verifica atualizações ao iniciar, se configurado."""
        cfg = _carregar_config_update()
        if not cfg.get("auto_check", True):
            return

        def _on_result(tem_update, info):
            if tem_update:
                self.root.after(0, lambda: self._notificar_update_disponivel(info))

        verificar_atualizacao_github(callback_resultado=_on_result)

    def _notificar_update_disponivel(self, info):
        """Mostra popup quando há atualização disponível."""
        resp = messagebox.askyesno(
            "Atualização Disponível",
            f"Nova versão disponível!\n\n"
            f"Versão atual: v{info['versao_atual']}\n"
            f"Nova versão: v{info['versao_nova']}\n\n"
            f"{info.get('notas', '')[:200]}\n\n"
            f"Deseja atualizar agora?"
        )
        if resp:
            self._executar_atualizacao(info)

    def _executar_atualizacao(self, info):
        """Executa o download e aplicação da atualização com janela de progresso."""
        jan = tk.Toplevel(self.root)
        jan.title("Atualizando TECH PRIME PLUS")
        jan.geometry("460x200")
        jan.configure(bg="#f0f0f0")
        jan.resizable(False, False)
        jan.grab_set()
        sw = jan.winfo_screenwidth(); sh = jan.winfo_screenheight()
        jan.geometry(f"460x200+{(sw-460)//2}+{(sh-200)//2}")

        tk.Label(jan, text="ATUALIZANDO O SISTEMA",
                 font=("Arial", 12, "bold"), bg="#f0f0f0", fg="#1a3a6c").pack(pady=(20, 10))

        lbl_status = tk.Label(jan, text="Iniciando download...",
                              font=("Arial", 10), bg="#f0f0f0", fg="#333")
        lbl_status.pack(pady=5)

        progress = ttk.Progressbar(jan, mode="indeterminate", length=360)
        progress.pack(pady=10)
        progress.start(15)

        btn_fechar = tk.Button(jan, text="FECHAR", bg="#1a3a6c", fg="white",
                               font=("Arial", 9, "bold"), relief="flat", padx=16, pady=5,
                               cursor="hand2", state="disabled",
                               command=jan.destroy)
        btn_fechar.pack(pady=10)

        def _progresso(etapa, msg):
            def _update():
                lbl_status.config(text=msg)
                if etapa == "concluido":
                    progress.stop()
                    progress.config(mode="determinate", value=100)
                    lbl_status.config(fg="#1e5631")
                    btn_fechar.config(state="normal")
                    btn_reiniciar = tk.Button(jan, text="REINICIAR AGORA", bg="#1e5631", fg="white",
                                              font=("Arial", 10, "bold"), relief="flat", padx=16, pady=6,
                                              cursor="hand2",
                                              command=lambda: self._reiniciar_app())
                    btn_reiniciar.pack(pady=(0, 10))
                elif etapa == "erro":
                    progress.stop()
                    lbl_status.config(fg="#721c24")
                    btn_fechar.config(state="normal")
            self.root.after(0, _update)

        baixar_e_aplicar_atualizacao(info["download_url"], callback_progresso=_progresso)

    def _reiniciar_app(self):
        """Reinicia a aplicação."""
        import sys
        python = sys.executable
        script = os.path.abspath(__file__)
        self.root.destroy()
        subprocess.Popen([python, script])
        sys.exit(0)

    def _on_tab_changed(self, event):
        """Constrói a aba na primeira vez que for acessada (lazy loading)."""
        aba = self.tab_control.select()
        if aba == str(self.tab_nav) and not self._aba_construida['nav']:
            self._aba_construida['nav'] = True
            self.criar_interface_navegador()
        elif aba == str(self.tab_custos) and not self._aba_construida['custos']:
            self._aba_construida['custos'] = True
            self.criar_interface_custos()
        elif aba == str(self.tab_logs) and not self._aba_construida['logs']:
            self._aba_construida['logs'] = True
            self.criar_interface_logs()
            self.atualizar_logs()
        elif aba == str(self.tab_config) and not self._aba_construida['config']:
            self._aba_construida['config'] = True
            self.criar_interface_config()

    def _iniciar_pos_boot(self):
        """Reservado para compatibilidade — boot agora é síncrono."""
        pass

    def conectar(self):
        return sqlite3.connect(self.db_file)

    def inicializar_banco(self):
        with self.conectar() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS clientes 
                           (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, whatsapp TEXT, 
                            valor REAL, vencimento TEXT, adicionado TEXT)''')
            try:
                conn.execute("ALTER TABLE clientes ADD COLUMN adicionado TEXT")
            except:
                pass
            try:
                conn.execute("ALTER TABLE clientes ADD COLUMN usuario TEXT")
            except:
                pass
            try:
                conn.execute("ALTER TABLE clientes ADD COLUMN senha TEXT")
            except:
                pass
            try:
                conn.execute("ALTER TABLE clientes ADD COLUMN painel TEXT")
            except:
                pass
            conn.execute('''CREATE TABLE IF NOT EXISTS paineis 
                           (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, url TEXT, usuario TEXT, senha TEXT)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS config
                           (chave TEXT PRIMARY KEY, valor TEXT)''')
            conn.execute("INSERT OR IGNORE INTO config (chave, valor) VALUES ('nome_empresa', 'TECH PRIME')")
            conn.execute('''CREATE TABLE IF NOT EXISTS custos
                           (id INTEGER PRIMARY KEY AUTOINCREMENT, descricao TEXT, valor REAL, data TEXT)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS logs
                           (id INTEGER PRIMARY KEY AUTOINCREMENT, tipo TEXT, descricao TEXT, data TEXT)''')
            try:
                conn.execute("ALTER TABLE logs ADD COLUMN usuario TEXT DEFAULT ''")
            except:
                pass
            conn.execute('''CREATE TABLE IF NOT EXISTS usuarios_sistema
                           (id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT UNIQUE, senha_hash TEXT)''')
            try:
                conn.execute("ALTER TABLE usuarios_sistema ADD COLUMN email TEXT NOT NULL DEFAULT ''")
            except: pass
            try:
                conn.execute("ALTER TABLE usuarios_sistema ADD COLUMN perfil TEXT NOT NULL DEFAULT 'completo'")
            except: pass
            try:
                conn.execute("ALTER TABLE usuarios_sistema ADD COLUMN permissoes TEXT NOT NULL DEFAULT ''")
            except: pass
            conn.execute('''CREATE TABLE IF NOT EXISTS wpp_mensagens
                           (id INTEGER PRIMARY KEY AUTOINCREMENT,
                            de TEXT, nome_contato TEXT, mensagem TEXT,
                            data TEXT, lida INTEGER DEFAULT 0)''')
            # Configs da API WhatsApp
            for chave, valor in [
                ('wpp_token',       ''),
                ('wpp_phone_id',    ''),
                ('wpp_verify_token','TECHPRIME2026'),
                ('wpp_webhook_port','8765'),
                ('wpp_auto_avisos', '0'),
                ('wpp_dias_aviso',  '3'),
            ]:
                conn.execute("INSERT OR IGNORE INTO config (chave, valor) VALUES (?,?)", (chave, valor))

    def executar_exclusao_automatica(self):
        """Remove clientes vencidos há mais de X dias, se configurado."""
        with self.conectar() as conn:
            row = conn.execute("SELECT valor FROM config WHERE chave='exclusao_auto_dias'").fetchone()
            if not row or not row[0]: return
            try:
                dias = int(row[0])
            except:
                return
            hoje = datetime.now().date()
            limite = hoje - timedelta(days=dias)
            clientes = conn.execute("SELECT id, nome, vencimento FROM clientes").fetchall()
            removidos = 0
            for cid, nome, venc in clientes:
                try:
                    dt = datetime.strptime(venc, "%d/%m/%Y").date()
                    if dt <= limite:
                        conn.execute("DELETE FROM clientes WHERE id=?", (cid,))
                        removidos += 1
                except:
                    pass
            if removidos > 0:
                with self.conectar() as conn2:
                    conn2.execute("INSERT INTO logs (tipo, descricao, data) VALUES (?,?,?)",
                                  ("EXCLUSÃO AUTO", f"{removidos} cliente(s) removido(s) por vencimento",
                                   datetime.now().strftime("%d/%m/%Y %H:%M:%S")))
                self.atualizar_tudo()

    def get_total_custos_mes(self):
        hoje = datetime.now()
        mes_atual = hoje.strftime("%m/%Y")
        with self.conectar() as conn:
            rows = conn.execute("SELECT valor, data FROM custos").fetchall()
            total = sum(v for v, d in rows if d and d[3:] == mes_atual)
            return total

    def get_receita_total(self):
        """Receita = soma de TODOS os clientes com vencimento no mês atual (mesmo critério em todo o sistema)."""
        hoje = datetime.now()
        fat = 0.0
        with self.conectar() as conn:
            for v, d in conn.execute("SELECT valor, vencimento FROM clientes"):
                try:
                    dt = datetime.strptime(d, "%d/%m/%Y").date()
                    if dt.month == hoje.month and dt.year == hoje.year:
                        fat += v
                except: pass
        return fat

    def get_nome_empresa(self):
        with self.conectar() as conn:
            row = conn.execute("SELECT valor FROM config WHERE chave='nome_empresa'").fetchone()
            return row[0] if row else "TECH PRIME"

    def salvar_nome_empresa(self, nome):
        with self.conectar() as conn:
            conn.execute("UPDATE config SET valor=? WHERE chave='nome_empresa'", (nome,))

    def get_mensagem_whatsapp(self):
        with self.conectar() as conn:
            row = conn.execute("SELECT valor FROM config WHERE chave='msg_whatsapp'").fetchone()
            return row[0] if row else "Olá {nome}, passando para lembrar que seu acesso aos canais {empresa} vence em {vencimento}. Deseja renovar?"

    def salvar_mensagem_whatsapp(self, msg):
        with self.conectar() as conn:
            conn.execute("INSERT OR REPLACE INTO config (chave, valor) VALUES ('msg_whatsapp', ?)", (msg,))

    def get_mensagem_vencido(self):
        with self.conectar() as conn:
            row = conn.execute("SELECT valor FROM config WHERE chave='msg_vencido'").fetchone()
            return row[0] if row else "Olá {nome}, seu acesso aos canais {empresa} venceu em {vencimento}. Renove agora para não ficar sem acesso!"

    def salvar_mensagem_vencido(self, msg):
        with self.conectar() as conn:
            conn.execute("INSERT OR REPLACE INTO config (chave, valor) VALUES ('msg_vencido', ?)", (msg,))

    def criar_interface_gestao(self):
        self.main = tk.Frame(self.tab_gestao, bg="#f0f0f0", padx=15, pady=10)
        self.main.pack(fill=tk.BOTH, expand=True)

        # ── Cabeçalho ──
        header = tk.Frame(self.main, bg="#f0f0f0")
        header.pack(fill=tk.X, pady=(0, 10))
        tk.Label(header, text="TECH PRIME PLUS", fg="#1a3a6c", bg="#f0f0f0",
                 font=('Arial', 16, 'bold')).pack(side=tk.LEFT)
        self.lbl_relogio = tk.Label(header, text="", fg="#333", bg="#f0f0f0",
                                     font=('Consolas', 18, 'bold'))
        self.lbl_relogio.pack(side=tk.RIGHT)
        self.lbl_data = tk.Label(header, text="", fg="#555", bg="#f0f0f0",
                                  font=('Arial', 10))
        self.lbl_data.pack(side=tk.RIGHT, padx=(0, 12))

        # ── Cards do dashboard ──
        dash = tk.Frame(self.main, bg="#f0f0f0")
        dash.pack(fill=tk.X, pady=(0, 10))
        self.c_tot = self.card_estilizado(dash, "TOTAL",          self.cores['total'],           filtro=None)
        self.c_atv = self.card_estilizado(dash, "ATIVOS",         self.cores['ativo']['dark'],   filtro="ativo")
        self.c_alt = self.card_estilizado(dash, "A VENCER",       self.cores['alerta']['dark'],  filtro="alerta")
        self.c_vnc = self.card_estilizado(dash, "VENCIDOS",       self.cores['vencido']['dark'], filtro="vencido")
        self.c_fin = self.card_estilizado(dash, "TOTAL EM ABERTO",self.cores['faturamento'],     filtro=None)

        # ── Barra de ações rápidas (botões mais usados) ──
        frame_acoes = tk.Frame(self.main, bg="#f0f0f0")
        frame_acoes.pack(fill=tk.X, pady=(0, 6))

        def ir_clientes():
            self.tab_control.select(self.tab_clientes)

        if "clientes" in self.permissoes:
            tk.Button(frame_acoes, text="➕ NOVO CLIENTE", bg="#1a3a6c", fg="white",
                      font=("Arial", 9, "bold"), relief="flat", padx=12, pady=5,
                      cursor="hand2", command=ir_clientes).pack(side=tk.LEFT, padx=(0, 4))
        if "renovar" in self.permissoes:
            tk.Button(frame_acoes, text="♻️ RENOVAR", bg="#1e5631", fg="white",
                      font=("Arial", 9, "bold"), relief="flat", padx=12, pady=5,
                      cursor="hand2", command=self.janela_renovacao).pack(side=tk.LEFT, padx=4)
        if "whatsapp" in self.permissoes:
            tk.Button(frame_acoes, text="📱 WHATSAPP", bg="#075e54", fg="white",
                      font=("Arial", 9, "bold"), relief="flat", padx=12, pady=5,
                      cursor="hand2", command=self.abrir_whatsapp).pack(side=tk.LEFT, padx=4)
            tk.Button(frame_acoes, text="📛 AVISAR VENCIDO", bg="#8B0000", fg="white",
                      font=("Arial", 9, "bold"), relief="flat", padx=12, pady=5,
                      cursor="hand2", command=self.disparar_avisos_vencidos).pack(side=tk.LEFT, padx=4)
        if "clientes" in self.permissoes:
            tk.Button(frame_acoes, text="✎ EDITAR", bg="#856404", fg="white",
                      font=("Arial", 9, "bold"), relief="flat", padx=12, pady=5,
                      cursor="hand2", command=self.carregar_edicao_cliente_na_aba).pack(side=tk.LEFT, padx=4)
        if "excluir" in self.permissoes:
            tk.Button(frame_acoes, text="🗑 EXCLUIR", bg="#721c24", fg="white",
                      font=("Arial", 9, "bold"), relief="flat", padx=12, pady=5,
                      cursor="hand2", command=self.excluir_cliente).pack(side=tk.LEFT, padx=4)
        tk.Button(frame_acoes, text="🔄 ATUALIZAR", bg="#2d6a9f", fg="white",
                  font=("Arial", 9, "bold"), relief="flat", padx=12, pady=5,
                  cursor="hand2", command=self.atualizar_tudo).pack(side=tk.RIGHT, padx=(4, 0))

        # ── Barra de Pesquisa ──
        frame_busca = tk.Frame(self.main, bg="#f0f0f0")
        frame_busca.pack(fill=tk.X, pady=(0, 5))
        tk.Label(frame_busca, text="🔍 Pesquisar:", bg="#f0f0f0",
                 font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        self.ent_busca = ttk.Entry(frame_busca, width=40, font=("Arial", 10))
        self.ent_busca.pack(side=tk.LEFT, padx=5)
        self.ent_busca.bind("<KeyRelease>", lambda e: self.filtrar_tabela())
        tk.Label(frame_busca, text="(nome, WhatsApp, usuário ou senha)",
                 bg="#f0f0f0", fg="#888", font=("Arial", 8, "italic")).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(frame_busca, text="✖ Limpar", command=self.limpar_busca).pack(side=tk.LEFT)

        # ── Rodapé financeiro (antes da tabela) ──
        frame_rodape = tk.Frame(self.main, bg="#0d1b2a", pady=7)
        frame_rodape.pack(side=tk.BOTTOM, fill=tk.X)
        self.lbl_rodape = tk.Label(frame_rodape, text="Carregando...", bg="#0d1b2a",
                                    fg="#FFD700", font=("Arial", 10, "bold"))
        self.lbl_rodape.pack(side=tk.LEFT, padx=14)

        # ── Tabela de clientes ──
        frame_tab = tk.Frame(self.main)
        frame_tab.pack(fill=tk.BOTH, expand=True)

        scroll_y = ttk.Scrollbar(frame_tab, orient="vertical")
        scroll_x = ttk.Scrollbar(frame_tab, orient="horizontal")
        self.tab = ttk.Treeview(frame_tab, columns=self.col_order, show='headings',
                                 yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        scroll_y.config(command=self.tab.yview)
        scroll_x.config(command=self.tab.xview)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.tab.pack(fill=tk.BOTH, expand=True)

        self.tab.tag_configure('ativo',   background="#e8f5e9")
        self.tab.tag_configure('alerta',  background="#fff3cd")
        self.tab.tag_configure('vencido', background=self.cores['vencido']['light'],
                                foreground=self.cores['vencido']['dark'])

        self._drag_col = None
        self._sort_col = None
        self._sort_asc = True
        self._aplicar_cabecalhos()
        self.tab.bind("<ButtonPress-1>",   self._col_drag_start)
        self.tab.bind("<B1-Motion>",       self._col_drag_motion)
        self.tab.bind("<ButtonRelease-1>", self._col_drag_end)
        self.tab.bind("<Double-Button-1>", self._col_sort_click)
        self.tab.bind("<Button-3>",        self._menu_copiar)

    def criar_interface_clientes(self):
        """Aba dedicada ao cadastro e gestão de clientes."""
        main = tk.Frame(self.tab_clientes, bg="#f0f0f0", padx=15, pady=12)
        main.pack(fill=tk.BOTH, expand=True)

        tk.Label(main, text="👥 GESTÃO DE CLIENTES", font=("Arial", 14, "bold"),
                 bg="#f0f0f0", fg="#1a3a6c").pack(anchor="w", pady=(0, 10))

        # ── Formulário de Cadastro ──
        form = tk.LabelFrame(main, text=" CADASTRO / EDIÇÃO ", bg="#d9d9d9",
                             padx=12, pady=12, font=("Arial", 9, "bold"))
        form.pack(fill=tk.X, pady=(0, 10))

        inf = tk.Frame(form, bg="#d9d9d9")
        inf.pack(fill=tk.X)

        # Linha 1
        tk.Label(inf, text="Nome:",     bg="#d9d9d9", font=("Arial", 9)).grid(row=0, column=0, sticky="e", padx=(0,4), pady=4)
        self.ent_nome    = ttk.Entry(inf, width=24); self.ent_nome.grid(row=0, column=1, padx=(0,14), pady=4)

        tk.Label(inf, text="Usuário:",  bg="#d9d9d9", font=("Arial", 9)).grid(row=0, column=2, sticky="e", padx=(0,4))
        self.ent_usuario = ttk.Entry(inf, width=18); self.ent_usuario.grid(row=0, column=3, padx=(0,14), pady=4)

        tk.Label(inf, text="Senha:",    bg="#d9d9d9", font=("Arial", 9)).grid(row=0, column=4, sticky="e", padx=(0,4))
        self.ent_senha   = ttk.Entry(inf, width=18); self.ent_senha.grid(row=0, column=5, padx=(0,14), pady=4)

        tk.Label(inf, text="WhatsApp:", bg="#d9d9d9", font=("Arial", 9)).grid(row=0, column=6, sticky="e", padx=(0,4))
        self.ent_zap     = ttk.Entry(inf, width=18); self.ent_zap.grid(row=0, column=7, pady=4)

        # Linha 2
        tk.Label(inf, text="Valor:",      bg="#d9d9d9", font=("Arial", 9)).grid(row=1, column=0, sticky="e", padx=(0,4), pady=4)
        self.ent_val     = ttk.Entry(inf, width=24); self.ent_val.grid(row=1, column=1, padx=(0,14), pady=4)

        tk.Label(inf, text="Venc.:",      bg="#d9d9d9", font=("Arial", 9)).grid(row=1, column=2, sticky="e", padx=(0,4))
        self.ent_venc    = DateEntry(inf, width=14, date_pattern="dd/mm/yyyy",
                                     background="#1a3a6c", foreground="white",
                                     borderwidth=2, locale="pt_BR")
        self.ent_venc.set_date(datetime.now() + timedelta(days=30))
        self.ent_venc.grid(row=1, column=3, padx=(0,14), pady=4)

        tk.Label(inf, text="Adicionado:", bg="#d9d9d9", font=("Arial", 9)).grid(row=1, column=4, sticky="e", padx=(0,4))
        self.ent_adicionado = ttk.Entry(inf, width=18, state='readonly')
        self.ent_adicionado.grid(row=1, column=5, padx=(0,14), pady=4)

        tk.Label(inf, text="Painel:",     bg="#d9d9d9", font=("Arial", 9)).grid(row=1, column=6, sticky="e", padx=(0,4))
        self.var_painel  = tk.StringVar(value="")
        self.cmb_painel  = ttk.Combobox(inf, textvariable=self.var_painel, state="readonly", width=16)
        self.cmb_painel.grid(row=1, column=7, pady=4)
        self._atualizar_combo_paineis()

        # ── Botões de ação — organizados em 2 linhas horizontais ──
        frame_btns = tk.Frame(main, bg="#f0f0f0")
        frame_btns.pack(fill=tk.X, pady=(0, 8))

        # Linha 1 de botões — ações de cadastro
        linha_bt1 = tk.Frame(frame_btns, bg="#f0f0f0")
        linha_bt1.pack(fill=tk.X, pady=(0, 4))

        def _btn(parent, texto, cor, fg, cmd, tooltip_txt):
            b = tk.Button(parent, text=texto, bg=cor, fg=fg,
                          font=("Arial", 9, "bold"), relief="flat",
                          padx=14, pady=7, cursor="hand2", command=cmd)
            b.pack(side=tk.LEFT, padx=3)
            Tooltip(b, tooltip_txt)
            return b

        _btn(linha_bt1, "💾 SALVAR",          "#1a3a6c", "white", self.salvar_dados,
             "Salva/atualiza o cliente e cria backup automático")
        _btn(linha_bt1, "✎ EDITAR",           "#856404",  "white", self.carregar_edicao_cliente,
             "Carrega o cliente selecionado para edição")
        _btn(linha_bt1, "🗑 EXCLUIR",          "#721c24",  "white", self.excluir_cliente,
             "Exclui o cliente selecionado (somente vencidos)")
        _btn(linha_bt1, "🧹 LIMPAR CAMPOS",   "#555555",  "white", self.limpar_campos,
             "Limpa o formulário para novo cadastro")
        _btn(linha_bt1, "🔄 ATUALIZAR",       "#2d6a9f",  "white", self.atualizar_tudo,
             "Recarrega a lista de clientes")

        # Separador visual
        tk.Frame(frame_btns, bg="#cccccc", height=1).pack(fill=tk.X, padx=2, pady=2)

        # Linha 2 de botões — ações sobre o cliente selecionado
        linha_bt2 = tk.Frame(frame_btns, bg="#f0f0f0")
        linha_bt2.pack(fill=tk.X, pady=(2, 0))

        _btn(linha_bt2, "♻️ RENOVAR",         "#1e5631",  "white", self.janela_renovacao,
             "Renova o plano do cliente selecionado")
        _btn(linha_bt2, "📱 WHATSAPP",         "#075e54",  "white", self.abrir_whatsapp,
             "Envia mensagem de lembrete no WhatsApp")
        _btn(linha_bt2, "📛 AVISAR VENCIDO",   "#8B0000",  "white", self.disparar_avisos_vencidos,
             "Envia mensagem de cobrança para cliente vencido")
        _btn(linha_bt2, "📑 PDF",              "#374151",  "white", self.exportar_pdf_manual,
             "Exporta relatório de todos os clientes em PDF")
        _btn(linha_bt2, "📊 EXCEL",            "#1e5631",  "white", self.exportar_excel,
             "Exporta dados para planilha Excel")
        _btn(linha_bt2, "📥 IMPORTAR",         "#1a3a6c",  "white", self.janela_importar_clientes,
             "Importa clientes de planilha ou TXT do painel")
        _btn(linha_bt2, "🛡️ BACKUP",           "#374151",  "white", self.fazer_backup_manual,
             "Cria uma cópia de segurança do banco de dados")
        _btn(linha_bt2, "💬 MENSAGENS",        "#6d28d9",  "white", self.janela_caixa_entrada,
             "Caixa de entrada WhatsApp — mensagens recebidas")

        # Badge de mensagens não lidas
        self.lbl_wpp_badge = tk.Label(linha_bt2, text="", bg="#f0f0f0", fg="#721c24",
                                       font=("Arial", 8, "bold"))
        self.lbl_wpp_badge.pack(side=tk.LEFT, padx=6)

        # ── Tabela espelho (sincronizada com o Painel Principal) ──
        tk.Label(main, text="Selecione um cliente abaixo para aplicar as ações:",
                 bg="#f0f0f0", fg="#555", font=("Arial", 8, "italic")).pack(anchor="w", pady=(0, 3))

        frame_tab2 = tk.Frame(main)
        frame_tab2.pack(fill=tk.BOTH, expand=True)

        scroll_y2 = ttk.Scrollbar(frame_tab2, orient="vertical")
        scroll_x2 = ttk.Scrollbar(frame_tab2, orient="horizontal")
        self.tab2 = ttk.Treeview(frame_tab2, columns=self.col_order, show='headings',
                                  yscrollcommand=scroll_y2.set, xscrollcommand=scroll_x2.set)
        scroll_y2.config(command=self.tab2.yview)
        scroll_x2.config(command=self.tab2.xview)
        scroll_y2.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x2.pack(side=tk.BOTTOM, fill=tk.X)
        self.tab2.pack(fill=tk.BOTH, expand=True)

        self.tab2.tag_configure('ativo',   background="#e8f5e9")
        self.tab2.tag_configure('alerta',  background="#fff3cd")
        self.tab2.tag_configure('vencido', background=self.cores['vencido']['light'],
                                 foreground=self.cores['vencido']['dark'])

        # Aplicar mesmos cabeçalhos
        for cid in self.col_order:
            cfg = self.col_config[cid]
            self.tab2.heading(cid, text=cfg["text"])
            self.tab2.column(cid, width=cfg["width"], minwidth=60, stretch=True, anchor='center')

        # Menu de clique direito na tab2
        self.tab2.bind("<Button-3>", self._menu_copiar2)

        # ── Barra de pesquisa própria da aba Clientes ──
        frame_busca2 = tk.Frame(main, bg="#f0f0f0")
        # Inserir antes da tabela — repack
        frame_busca2.pack(fill=tk.X, pady=(0, 4), before=frame_tab2)

        tk.Label(frame_busca2, text="🔍 Filtrar:", bg="#f0f0f0",
                 font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        self.ent_busca2 = ttk.Entry(frame_busca2, width=35, font=("Arial", 10))
        self.ent_busca2.pack(side=tk.LEFT, padx=5)
        self.ent_busca2.bind("<KeyRelease>", lambda e: self._filtrar_tab2())
        ttk.Button(frame_busca2, text="✖ Limpar",
                   command=lambda: [self.ent_busca2.delete(0, tk.END), self._filtrar_tab2()]
                   ).pack(side=tk.LEFT)

    def _menu_copiar2(self, event):
        """Menu de contexto clique direito na tab2 (aba Clientes)."""
        iid = self.tab2.identify_row(event.y)
        if not iid:
            return
        self.tab2.selection_set(iid)
        # Espelha seleção na tab principal também
        mapa = dict(zip(self.col_order, self.tab2.item(iid)['values']))
        menu = tk.Menu(self.root, tearoff=0)
        menu.configure(font=("Arial", 9))
        def copiar(valor):
            self.root.clipboard_clear()
            self.root.clipboard_append(str(valor))
            self.root.update()
        menu.add_command(label=f"📋  Copiar Nome:       {mapa.get('N','')}", command=lambda: copiar(mapa.get('N','')))
        menu.add_command(label=f"📋  Copiar Usuário:    {mapa.get('U','')}", command=lambda: copiar(mapa.get('U','')))
        menu.add_command(label=f"📋  Copiar Senha:      {mapa.get('P','')}", command=lambda: copiar(mapa.get('P','')))
        menu.add_separator()
        menu.add_command(label=f"📋  Copiar Painel:     {mapa.get('PNL','')}", command=lambda: copiar(mapa.get('PNL','')))
        menu.add_command(label=f"📋  Copiar WhatsApp:   {mapa.get('W','')}", command=lambda: copiar(mapa.get('W','')))
        menu.add_command(label=f"📋  Copiar Vencimento: {mapa.get('D','')}", command=lambda: copiar(mapa.get('D','')))
        menu.tk_popup(event.x_root, event.y_root)

    def _filtrar_tab2(self):
        """Filtra a tabela espelho na aba Clientes."""
        if not hasattr(self, 'tab2'):
            return
        termo = self.ent_busca2.get().strip().lower()
        for i in self.tab2.get_children():
            self.tab2.delete(i)
        hoje = datetime.now().date()
        with self.conectar() as conn:
            for n, z, u, p, pnl, v, d, ad in conn.execute(
                    "SELECT nome, whatsapp, usuario, senha, painel, valor, vencimento, adicionado "
                    "FROM clientes ORDER BY nome COLLATE NOCASE ASC"):
                if termo:
                    campos = [(n or "").lower(), (z or "").lower(),
                              (u or "").lower(), (p or "").lower()]
                    if not any(termo in c for c in campos):
                        continue
                try:
                    dt = datetime.strptime(d, "%d/%m/%Y").date()
                    if dt < hoje:   tag, st = 'vencido', "Vencido"
                    elif (dt - hoje).days <= 5: tag, st = 'alerta', "Alerta"
                    else:           tag, st = 'ativo',   "Ativo"
                    self.tab2.insert("", "end",
                                     values=self._row_values(n, z, u, p, pnl, v, d, ad, st),
                                     tags=(tag,))
                except:
                    pass

    def carregar_edicao_cliente_na_aba(self):
        """Carrega cliente selecionado no Painel e vai para aba Clientes."""
        sel = self.tab.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Selecione um cliente na tabela!"); return
        self.carregar_edicao_cliente()
        self.tab_control.select(self.tab_clientes)

    def _tab_ativa_sel(self):
        """Retorna (treeview_ativo, seleção) conforme a aba atual.
        Aba Clientes usa tab2; demais usam tab."""
        try:
            aba_atual = self.tab_control.select()
            if aba_atual == str(self.tab_clientes):
                sel = self.tab2.selection()
                return self.tab2, sel
        except: pass
        return self.tab, self.tab.selection()

    def _aplicar_cabecalhos(self):
        self.tab["columns"] = self.col_order
        for cid in self.col_order:
            cfg = self.col_config[cid]
            label = cfg["text"]
            if cid == self._sort_col:
                label += "  ▲" if self._sort_asc else "  ▼"
            self.tab.heading(cid, text=label)
            self.tab.column(cid, width=cfg["width"], minwidth=60, stretch=True, anchor='center')

    def _menu_copiar(self, event):
        """Menu de contexto com clique direito para copiar campos."""
        iid = self.tab.identify_row(event.y)
        if not iid:
            return
        self.tab.selection_set(iid)
        mapa = dict(zip(self.col_order, self.tab.item(iid)['values']))

        menu = tk.Menu(self.root, tearoff=0)
        menu.configure(font=("Arial", 9))

        def copiar(valor):
            self.root.clipboard_clear()
            self.root.clipboard_append(str(valor))
            self.root.update()

        menu.add_command(label=f"📋  Copiar Nome:       {mapa.get('N','')}", command=lambda: copiar(mapa.get('N','')))
        menu.add_command(label=f"📋  Copiar Usuário:    {mapa.get('U','')}", command=lambda: copiar(mapa.get('U','')))
        menu.add_command(label=f"📋  Copiar Senha:      {mapa.get('P','')}", command=lambda: copiar(mapa.get('P','')))
        menu.add_separator()
        menu.add_command(label=f"📋  Copiar Painel:     {mapa.get('PNL','')}", command=lambda: copiar(mapa.get('PNL','')))
        menu.add_command(label=f"📋  Copiar WhatsApp:   {mapa.get('W','')}", command=lambda: copiar(mapa.get('W','')))
        menu.add_command(label=f"📋  Copiar Vencimento: {mapa.get('D','')}", command=lambda: copiar(mapa.get('D','')))
        menu.tk_popup(event.x_root, event.y_root)

    def _col_sort_click(self, event):
        """Ordena qualquer coluna ao dar duplo clique no cabeçalho."""
        if self.tab.identify_region(event.x, event.y) != "heading":
            return
        col_id = self.tab.identify_column(event.x)
        idx = int(col_id.replace("#", "")) - 1
        if idx < 0 or idx >= len(self.col_order):
            return
        cid = self.col_order[idx]
        if self._sort_col == cid:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = cid
            self._sort_asc = True
        self._ordenar_tabela()

    def _ordenar_tabela(self):
        """Reordena as linhas pela coluna clicada com detecção automática de tipo."""
        rows = [(self.tab.item(iid)["values"], self.tab.item(iid)["tags"], iid)
                for iid in self.tab.get_children()]
        col_idx = self.col_order.index(self._sort_col)

        def sort_key(val):
            s = str(val).strip()
            for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
                try:
                    return (0, datetime.strptime(s[:16] if len(s) > 10 else s, fmt))
                except:
                    pass
            try:
                clean = s.replace("R$","").replace(".","").replace(",",".").strip()
                return (1, float(clean))
            except:
                pass
            return (2, s.lower())

        rows.sort(key=lambda r: sort_key(r[0][col_idx]), reverse=not self._sort_asc)
        for values, tags, iid in rows:
            self.tab.move(iid, "", "end")
        for values, tags, iid in rows:
            if tags:
                self.tab.item(iid, tags=tags)
        self._aplicar_cabecalhos()

    def _col_drag_start(self, event):
        if self.tab.identify_region(event.x, event.y) == "heading":
            self._drag_col = self.tab.identify_column(event.x)

    def _col_drag_motion(self, event):
        if self._drag_col: self.tab.config(cursor="fleur")

    def _col_drag_end(self, event):
        if self._drag_col:
            self.tab.config(cursor="")
            target_col = self.tab.identify_column(event.x)
            if target_col and target_col != self._drag_col:
                src_idx = int(self._drag_col.replace("#", "")) - 1
                dst_idx = int(target_col.replace("#", "")) - 1
                if 0 <= src_idx < len(self.col_order) and 0 <= dst_idx < len(self.col_order):
                    col = self.col_order.pop(src_idx)
                    self.col_order.insert(dst_idx, col)
                    self._aplicar_cabecalhos()
                    self.atualizar_tudo()
        self._drag_col = None

    def _row_values(self, n, z, u, p, pnl, v, d, adicionado, st):
        try:
            valor_fmt = f"R$ {float(v):.2f}" if v is not None else "R$ 0,00"
        except (ValueError, TypeError):
            valor_fmt = "R$ 0,00"
        mapa = {
            "N":   str(n   or ""),
            "W":   str(z   or ""),
            "U":   str(u   or ""),
            "P":   str(p   or ""),
            "PNL": str(pnl or ""),
            "V":   valor_fmt,
            "D":   str(d   or ""),
            "A":   str(adicionado or ""),
            "S":   str(st  or ""),
        }
        return tuple(mapa[c] for c in self.col_order)

    def _atualizar_combo_paineis(self):
        """Atualiza o combobox de painéis com os painéis cadastrados."""
        try:
            with self.conectar() as conn:
                nomes = [r[0] for r in conn.execute("SELECT nome FROM paineis ORDER BY nome").fetchall()]
            self.cmb_painel["values"] = [""] + nomes
        except:
            pass

    def fazer_backup_manual(self):
        try:
            p = filedialog.asksaveasfilename(
                initialfile=f"BACKUP_TECHPRIME_{datetime.now().strftime('%d_%m_%Y')}.db",
                defaultextension=".db",
                filetypes=[("Database", "*.db")]
            )
            if p:
                shutil.copy2(self.db_file, p)
                messagebox.showinfo("Sucesso", "Backup manual concluído!")
        except Exception as e:
            messagebox.showerror("Erro", f"Falha no backup: {e}")

    def backup_automatico(self):
        """Cria uma pasta de backup e salva uma cópia silenciosa"""
        try:
            if not os.path.exists("backups_automaticos"):
                os.makedirs("backups_automaticos")
            data_str = datetime.now().strftime("%d_%m_%Y")
            destino = os.path.join("backups_automaticos", f"auto_backup_{data_str}.db")
            shutil.copy2(self.db_file, destino)
        except:
            pass

    def salvar_dados(self):
        n, z, v_raw, d = self.ent_nome.get().strip(), self.ent_zap.get().strip(), self.ent_val.get().strip(), self.ent_venc.get()
        usuario = self.ent_usuario.get().strip()
        senha   = self.ent_senha.get().strip()
        painel  = self.var_painel.get().strip()
        adicionado = datetime.now().strftime("%d/%m/%Y %H:%M")
        zap_limpo = ''.join(filter(str.isdigit, z))
        if not n or not v_raw or len(zap_limpo) < 11:
            messagebox.showwarning("Aviso", "Preencha Nome, WhatsApp (com DDD + 9 dígitos, ex: 11912345678) e Valor corretamente!"); return
        try:
            val = float(v_raw.replace(',', '.'))
            with self.conectar() as conn:
                editando_id = getattr(self, '_editando_id', None)
                if editando_id:
                    row = conn.execute("SELECT adicionado FROM clientes WHERE id=?", (editando_id,)).fetchone()
                    data_orig = row[0] if row else adicionado
                    conn.execute("UPDATE clientes SET nome=?, whatsapp=?, valor=?, vencimento=?, adicionado=?, usuario=?, senha=?, painel=? WHERE id=?",
                                 (n, z, val, d, data_orig, usuario, senha, painel, editando_id))
                    self._editando_id = None
                else:
                    conn.execute("INSERT INTO clientes (nome, whatsapp, valor, vencimento, adicionado, usuario, senha, painel) VALUES (?,?,?,?,?,?,?,?)",
                                 (n, z, val, d, adicionado, usuario, senha, painel))
            acao = "EDIÇÃO" if editando_id else "CADASTRO"
            with self.conectar() as conn2:
                conn2.execute("INSERT INTO logs (tipo, descricao, data, usuario) VALUES (?,?,?,?)",
                              (acao, f"Cliente: {n} | WhatsApp: {z} | Valor: R$ {val:.2f}",
                               datetime.now().strftime("%d/%m/%Y %H:%M:%S"), self.usuario_logado))
            self.backup_automatico()
            self.atualizar_tudo()
            self.limpar_campos()
        except: messagebox.showerror("Erro", "Formato de valor inválido.")

    def carregar_edicao_cliente(self):
        tree, sel = self._tab_ativa_sel()
        if not sel: return
        mapa = dict(zip(self.col_order, tree.item(sel[0])['values']))
        nome = mapa.get("N", "")
        self.ent_nome.delete(0, tk.END); self.ent_nome.insert(0, nome)
        self.ent_zap.delete(0, tk.END);  self.ent_zap.insert(0, mapa.get("W", ""))
        self.ent_val.delete(0, tk.END);  self.ent_val.insert(0, str(mapa.get("V", "")).replace('R$ ', '').replace(',', '.'))
        try:
            data_str = str(mapa.get("D", ""))
            if data_str:
                dt_venc = datetime.strptime(data_str, "%d/%m/%Y")
                self.ent_venc.set_date(dt_venc)
        except: pass
        with self.conectar() as conn:
            row = conn.execute("SELECT id, usuario, senha, painel FROM clientes WHERE nome=?", (nome,)).fetchone()
            if row:
                self._editando_id = row[0]
                self.ent_usuario.delete(0, tk.END); self.ent_usuario.insert(0, row[1] or "")
                self.ent_senha.delete(0, tk.END);   self.ent_senha.insert(0, row[2] or "")
                self._atualizar_combo_paineis()
                self.var_painel.set(row[3] or "")

    def abrir_whatsapp(self):
        """Tenta enviar via API; se não configurado, abre no navegador."""
        tree, sel = self._tab_ativa_sel()
        if not sel: return
        mapa = dict(zip(self.col_order, tree.item(sel[0])['values']))
        empresa = self.get_nome_empresa()
        template = self.get_mensagem_whatsapp()
        texto = template.replace("{nome}", mapa['N']).replace("{empresa}", empresa).replace("{vencimento}", mapa['D'])
        z = ''.join(filter(str.isdigit, str(mapa['W'])))

        token    = self._get_config('wpp_token')
        phone_id = self._get_config('wpp_phone_id')

        if token and phone_id and REQUESTS_OK:
            self._wpp_enviar_texto(f"55{z}", texto, nome_cliente=mapa['N'])
        else:
            msg = urllib.parse.quote(texto)
            webbrowser.open(f"https://api.whatsapp.com/send?phone=55{z}&text={msg}")

    # ── Helpers de config ──────────────────────────────────────────────────────
    def _get_config(self, chave):
        with self.conectar() as conn:
            row = conn.execute("SELECT valor FROM config WHERE chave=?", (chave,)).fetchone()
            return row[0] if row else ""

    def _set_config(self, chave, valor):
        with self.conectar() as conn:
            conn.execute("INSERT OR REPLACE INTO config (chave, valor) VALUES (?,?)", (chave, valor))

    # ── Envio via Meta API ─────────────────────────────────────────────────────
    def _wpp_enviar_texto(self, numero, texto, nome_cliente=""):
        """Envia mensagem de texto via Meta WhatsApp Business API."""
        if not REQUESTS_OK:
            messagebox.showerror("Erro", "Instale o pacote 'requests':\n pip install requests"); return False
        token    = self._get_config('wpp_token')
        phone_id = self._get_config('wpp_phone_id')
        if not token or not phone_id:
            messagebox.showwarning("API não configurada",
                "Configure o Token e o Phone Number ID\nna aba Configurações → WhatsApp API."); return False
        url  = f"https://graph.facebook.com/v19.0/{phone_id}/messages"
        hdrs = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        body = {
            "messaging_product": "whatsapp",
            "to": numero,
            "type": "text",
            "text": {"body": texto}
        }
        try:
            r = requests.post(url, headers=hdrs, json=body, timeout=10)
            data = r.json()
            if r.status_code == 200 and "messages" in data:
                with self.conectar() as conn:
                    conn.execute("INSERT INTO logs (tipo, descricao, data, usuario) VALUES (?,?,?,?)",
                                 ("WPP ENVIADO",
                                  f"Para: {numero} | Cliente: {nome_cliente} | Msg: {texto[:60]}...",
                                  datetime.now().strftime("%d/%m/%Y %H:%M:%S"), self.usuario_logado))
                return True
            else:
                erro = data.get("error", {}).get("message", str(data))
                messagebox.showerror("Erro ao enviar", f"Meta API retornou:\n{erro}")
                return False
        except Exception as e:
            messagebox.showerror("Erro de conexão", str(e))
            return False

    def _wpp_enviar_template(self, numero, template_name, lang="pt_BR"):
        """Envia um template aprovado pela Meta."""
        if not REQUESTS_OK: return False
        token    = self._get_config('wpp_token')
        phone_id = self._get_config('wpp_phone_id')
        if not token or not phone_id: return False
        url  = f"https://graph.facebook.com/v19.0/{phone_id}/messages"
        hdrs = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        body = {
            "messaging_product": "whatsapp",
            "to": numero,
            "type": "template",
            "template": {"name": template_name, "language": {"code": lang}}
        }
        try:
            r = requests.post(url, headers=hdrs, json=body, timeout=10)
            return r.status_code == 200
        except:
            return False

    # ── Avisos automáticos de vencimento ──────────────────────────────────────
    def disparar_avisos_vencimento(self, silencioso=False):
        """Envia WhatsApp para todos os clientes que vencem nos próximos N dias."""
        if not REQUESTS_OK or not self._get_config('wpp_token'):
            if not silencioso:
                messagebox.showwarning("API não configurada",
                    "Configure o Token na aba Configurações → WhatsApp API.")
            return
        dias = int(self._get_config('wpp_dias_aviso') or 3)
        hoje = datetime.now().date()
        limite = hoje + timedelta(days=dias)
        empresa  = self.get_nome_empresa()
        template = self.get_mensagem_whatsapp()
        enviados = 0
        with self.conectar() as conn:
            clientes = conn.execute(
                "SELECT nome, whatsapp, vencimento FROM clientes").fetchall()
        for nome, zap, venc in clientes:
            try:
                dt = datetime.strptime(venc, "%d/%m/%Y").date()
                if hoje <= dt <= limite:
                    z = ''.join(filter(str.isdigit, str(zap)))
                    if len(z) >= 10:
                        texto = template.replace("{nome}", nome).replace(
                            "{empresa}", empresa).replace("{vencimento}", venc)
                        ok = self._wpp_enviar_texto(f"55{z}", texto, nome_cliente=nome)
                        if ok: enviados += 1
            except: pass
        if not silencioso:
            messagebox.showinfo("Avisos enviados",
                f"✅ {enviados} aviso(s) enviado(s) para clientes a vencer em {dias} dia(s).")

    def disparar_avisos_vencidos(self):
        """Envia WhatsApp de lembrete de vencido para o cliente SELECIONADO na tabela."""
        tree, sel = self._tab_ativa_sel()
        if not sel:
            messagebox.showwarning("Aviso", "Selecione um cliente na tabela!"); return

        mapa = dict(zip(self.col_order, tree.item(sel[0])['values']))

        # Só envia se o cliente estiver vencido
        try:
            dt = datetime.strptime(mapa['D'], "%d/%m/%Y").date()
            if dt >= datetime.now().date():
                messagebox.showwarning("Aviso",
                    f"{mapa['N']} não está vencido!\n"
                    "Use o botão 📱 WHATSAPP para clientes ativos/a vencer."); return
        except:
            pass

        empresa  = self.get_nome_empresa()
        template = self.get_mensagem_vencido()
        texto    = (template
                    .replace("{nome}",       mapa['N'])
                    .replace("{empresa}",    empresa)
                    .replace("{vencimento}", mapa['D']))
        z = ''.join(filter(str.isdigit, str(mapa['W'])))

        token    = self._get_config('wpp_token')
        phone_id = self._get_config('wpp_phone_id')

        if token and phone_id and REQUESTS_OK:
            self._wpp_enviar_texto(f"55{z}", texto, nome_cliente=mapa['N'])
        else:
            msg_enc = urllib.parse.quote(texto)
            webbrowser.open(f"https://api.whatsapp.com/send?phone=55{z}&text={msg_enc}")

    # ── Iniciar atualização automática ────────────────────────────────────────
    def iniciar_atualizacao_automatica(self):
        """Agenda verificações periódicas a cada 5 minutos."""
        self.executar_exclusao_automatica()
        if self._get_config('wpp_auto_avisos') == '1':
            threading.Thread(target=lambda: self.disparar_avisos_vencimento(silencioso=True),
                             daemon=True).start()
        self.root.after(5 * 60 * 1000, self._ciclo_automatico)

    def _ciclo_automatico(self):
        """Ciclo que roda a cada 5 minutos após o boot."""
        self.atualizar_tudo()
        self.executar_exclusao_automatica()
        if self._get_config('wpp_auto_avisos') == '1':
            threading.Thread(target=lambda: self.disparar_avisos_vencimento(silencioso=True),
                             daemon=True).start()
        self.root.after(5 * 60 * 1000, self._ciclo_automatico)

    # ── Webhook — receber respostas ────────────────────────────────────────────
    def iniciar_webhook(self):
        """Sobe um servidor HTTP local para receber mensagens do Webhook da Meta."""
        port = int(self._get_config('wpp_webhook_port') or 8765)
        verify_token = self._get_config('wpp_verify_token')
        app_self = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a): pass  # silencia logs no console

            def do_GET(self):
                # Verificação do webhook pela Meta
                from urllib.parse import urlparse, parse_qs
                qs = parse_qs(urlparse(self.path).query)
                if qs.get("hub.verify_token", [""])[0] == verify_token:
                    challenge = qs.get("hub.challenge", [""])[0]
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(challenge.encode())
                else:
                    self.send_response(403); self.end_headers()

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body   = self.rfile.read(length)
                self.send_response(200); self.end_headers()
                try:
                    data = json.loads(body)
                    for entry in data.get("entry", []):
                        for change in entry.get("changes", []):
                            val = change.get("value", {})
                            for msg in val.get("messages", []):
                                if msg.get("type") == "text":
                                    de      = msg.get("from", "")
                                    texto   = msg["text"]["body"]
                                    contato = val.get("contacts", [{}])[0].get(
                                        "profile", {}).get("name", de)
                                    app_self._wpp_salvar_mensagem_recebida(de, contato, texto)
                except: pass

        def rodar():
            try:
                srv = HTTPServer(("0.0.0.0", port), Handler)
                app_self._webhook_server = srv
                srv.serve_forever()
            except Exception as e:
                pass

        threading.Thread(target=rodar, daemon=True).start()
        return port

    def _wpp_salvar_mensagem_recebida(self, de, contato, mensagem):
        with self.conectar() as conn:
            conn.execute(
                "INSERT INTO wpp_mensagens (de, nome_contato, mensagem, data, lida) VALUES (?,?,?,?,0)",
                (de, contato, mensagem, datetime.now().strftime("%d/%m/%Y %H:%M:%S")))
        # Notifica na thread principal
        self.root.after(0, self._notificar_mensagem, contato, mensagem)

    def _notificar_mensagem(self, contato, mensagem):
        """Pisca o título da janela para avisar nova mensagem."""
        self.root.title(f"💬 NOVA MENSAGEM de {contato} — TECH PRIME PLUS")
        self.root.after(3000, lambda: self.root.title("TECH PRIME PLUS"))
        if hasattr(self, 'lbl_wpp_badge'):
            total = self._total_nao_lidas()
            self.lbl_wpp_badge.config(text=f"💬 {total} não lida(s)" if total else "")

    def _total_nao_lidas(self):
        with self.conectar() as conn:
            return conn.execute("SELECT COUNT(*) FROM wpp_mensagens WHERE lida=0").fetchone()[0]

    # ── Janela caixa de entrada ────────────────────────────────────────────────
    def janela_caixa_entrada(self):
        jan = tk.Toplevel(self.root)
        jan.title("💬 Caixa de Entrada — WhatsApp")
        jan.geometry("820x540")
        jan.configure(bg="#f0f0f0")
        jan.resizable(True, True)
        jan.update_idletasks()
        sw = jan.winfo_screenwidth(); sh = jan.winfo_screenheight()
        jan.geometry(f"820x540+{(sw-820)//2}+{(sh-540)//2}")

        tk.Label(jan, text="💬 CAIXA DE ENTRADA — WHATSAPP",
                 font=("Arial", 12, "bold"), bg="#f0f0f0", fg="#1a3a6c").pack(pady=(10, 4))

        frame_tab = tk.Frame(jan); frame_tab.pack(fill="both", expand=True, padx=15, pady=(0,4))
        cols = ["ID", "DE", "CONTATO", "MENSAGEM", "DATA", "LIDA"]
        tree = ttk.Treeview(frame_tab, columns=cols, show="headings")
        sy = ttk.Scrollbar(frame_tab, orient="vertical",   command=tree.yview)
        sx = ttk.Scrollbar(frame_tab, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        sy.pack(side=tk.RIGHT, fill=tk.Y); sx.pack(side=tk.BOTTOM, fill=tk.X)
        tree.pack(fill="both", expand=True)

        larguras = {"ID":40,"DE":120,"CONTATO":140,"MENSAGEM":320,"DATA":130,"LIDA":50}
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, width=larguras[c], anchor="center" if c!="MENSAGEM" else "w")
        tree.tag_configure("nao_lida", background="#fff3cd")

        def carregar():
            for i in tree.get_children(): tree.delete(i)
            with self.conectar() as conn:
                for row in conn.execute(
                        "SELECT id, de, nome_contato, mensagem, data, lida FROM wpp_mensagens ORDER BY id DESC"):
                    tag = () if row[5] else ("nao_lida",)
                    tree.insert("", "end", values=(row[0], row[1], row[2], row[3], row[4],
                                                   "✅" if row[5] else "🔵"), tags=tag)
            if hasattr(self, 'lbl_wpp_badge'):
                total = self._total_nao_lidas()
                self.lbl_wpp_badge.config(text=f"💬 {total} não lida(s)" if total else "")
        carregar()

        def marcar_lida():
            sel = tree.selection()
            if not sel: return
            ids = [tree.item(s)['values'][0] for s in sel]
            with self.conectar() as conn:
                for mid in ids:
                    conn.execute("UPDATE wpp_mensagens SET lida=1 WHERE id=?", (mid,))
            carregar()

        def responder():
            sel = tree.selection()
            if not sel: return
            vals = tree.item(sel[0])['values']
            numero, contato = str(vals[1]), str(vals[2])
            jan_r = tk.Toplevel(jan)
            jan_r.title(f"Responder para {contato}")
            jan_r.geometry("500x200"); jan_r.configure(bg="#f0f0f0"); jan_r.grab_set()
            tk.Label(jan_r, text=f"Responder para: {contato} ({numero})",
                     bg="#f0f0f0", font=("Arial", 9, "bold")).pack(pady=(10,4), padx=10, anchor="w")
            txt = tk.Text(jan_r, height=5, font=("Arial", 10), relief="solid", bd=1)
            txt.pack(fill="x", padx=10, pady=4)
            def enviar_resp():
                msg = txt.get("1.0", "end-1c").strip()
                if msg:
                    ok = self._wpp_enviar_texto(numero, msg, nome_cliente=contato)
                    if ok: jan_r.destroy(); marcar_lida()
            tk.Button(jan_r, text="📤 ENVIAR", bg="#1a3a6c", fg="white",
                      font=("Arial", 10, "bold"), relief="flat",
                      command=enviar_resp).pack(pady=6)

        def excluir_msgs():
            sel = tree.selection()
            if not sel: return
            if not messagebox.askyesno("Excluir", f"Excluir {len(sel)} mensagem(ns)?"): return
            ids = [tree.item(s)['values'][0] for s in sel]
            with self.conectar() as conn:
                for mid in ids: conn.execute("DELETE FROM wpp_mensagens WHERE id=?", (mid,))
            carregar()

        frame_btns = tk.Frame(jan, bg="#f0f0f0"); frame_btns.pack(pady=6)
        ttk.Button(frame_btns, text="✅ Marcar lida(s)",  command=marcar_lida).pack(side=tk.LEFT, padx=4)
        ttk.Button(frame_btns, text="↩️ Responder",      command=responder).pack(side=tk.LEFT, padx=4)
        ttk.Button(frame_btns, text="🗑 Excluir",         command=excluir_msgs).pack(side=tk.LEFT, padx=4)
        ttk.Button(frame_btns, text="🔄 Atualizar",       command=carregar).pack(side=tk.LEFT, padx=4)

    def excluir_cliente(self):
        tree, sel = self._tab_ativa_sel()
        if not sel: return
        mapa = dict(zip(self.col_order, tree.item(sel[0])['values']))
        if mapa.get("S") != "Vencido": messagebox.showerror("Erro", "Só pode excluir clientes vencidos!"); return
        if messagebox.askyesno("Excluir", f"Remover {mapa['N']}?"):
            with self.conectar() as conn:
                conn.execute("DELETE FROM clientes WHERE nome=?", (mapa['N'],))
                conn.execute("INSERT INTO logs (tipo, descricao, data, usuario) VALUES (?,?,?,?)",
                             ("EXCLUSÃO", f"Cliente removido: {mapa['N']} | WhatsApp: {mapa.get('W','')}",
                              datetime.now().strftime("%d/%m/%Y %H:%M:%S"), self.usuario_logado))
            self.atualizar_tudo()

    def janela_renovacao(self):
        tree, sel = self._tab_ativa_sel()
        if not sel:
            messagebox.showwarning("Aviso", "Selecione um cliente para renovar!")
            return
        mapa = dict(zip(self.col_order, tree.item(sel[0])['values']))
        nome_cliente = mapa['N']
        data_venc_atual = datetime.strptime(mapa['D'], "%d/%m/%Y")
        hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        # Base de cálculo: se o cliente já venceu, renova a partir de HOJE
        # Se ainda está ativo/alerta, renova a partir da data de vencimento
        base_renovacao = hoje if data_venc_atual < hoje else data_venc_atual

        janela = tk.Toplevel(self.root)
        janela.title(f"Renovar - {nome_cliente}")
        janela.geometry("320x460")
        janela.configure(bg="#f0f0f0")
        janela.resizable(False, False)
        janela.grab_set()

        # Centralizar na tela
        janela.update_idletasks()
        sw = janela.winfo_screenwidth(); sh = janela.winfo_screenheight()
        janela.geometry(f"320x460+{(sw-320)//2}+{(sh-460)//2}")

        tk.Label(janela, text="SELECIONE O PLANO", font=("Arial", 11, "bold"),
                 bg="#f0f0f0", fg="#1a3a6c").pack(pady=(15, 2))

        # Informação da base de cálculo
        info_base = f"Base: {'HOJE ' + hoje.strftime('%d/%m/%Y') + ' (cliente vencido)' if data_venc_atual < hoje else 'Vencimento ' + data_venc_atual.strftime('%d/%m/%Y')}"
        tk.Label(janela, text=info_base, font=("Arial", 8, "italic"),
                 bg="#f0f0f0", fg="#555").pack(pady=(0, 10))

        def processar_renovacao(meses=None, dias=None):
            if dias is not None:
                nova_data = base_renovacao + timedelta(days=dias)
            else:
                nova_data = base_renovacao + relativedelta(months=meses)
            with self.conectar() as conn:
                conn.execute("UPDATE clientes SET vencimento=? WHERE nome=?",
                             (nova_data.strftime("%d/%m/%Y"), nome_cliente))
            with self.conectar() as conn2:
                conn2.execute("INSERT INTO logs (tipo, descricao, data, usuario) VALUES (?,?,?,?)",
                              ("RENOVAÇÃO", f"Cliente: {nome_cliente} | Novo vencimento: {nova_data.strftime('%d/%m/%Y')}",
                               datetime.now().strftime("%d/%m/%Y %H:%M:%S"), self.usuario_logado))
            self.atualizar_tudo()
            messagebox.showinfo("Sucesso", f"Renovado até {nova_data.strftime('%d/%m/%Y')}")
            janela.destroy()

        estilo_btn = {"width": 26, "pady": 8, "font": ("Arial", 9, "bold")}
        # Botão de confiança — destaque laranja
        tk.Button(janela, text="⏱ 3 DIAS (Confiança)", bg="#ff8c00", fg="white",
                  command=lambda: processar_renovacao(dias=3), **estilo_btn).pack(pady=4)
        tk.Frame(janela, bg="#cccccc", height=1).pack(fill="x", padx=20, pady=4)
        tk.Button(janela, text="1 MÊS (Mensal)",        bg="#e3f2fd", command=lambda: processar_renovacao(meses=1),  **estilo_btn).pack(pady=4)
        tk.Button(janela, text="3 MESES (Trimestral)",  bg="#bbdefb", command=lambda: processar_renovacao(meses=3),  **estilo_btn).pack(pady=4)
        tk.Button(janela, text="6 MESES (Semestral)",   bg="#90caf9", command=lambda: processar_renovacao(meses=6),  **estilo_btn).pack(pady=4)
        tk.Button(janela, text="1 ANO (Anual)",         bg="#1a3a6c", fg="white",
                  command=lambda: processar_renovacao(meses=12), **estilo_btn).pack(pady=4)
        tk.Button(janela, text="CANCELAR", bg="#f8d7da", fg="#721c24",
                  command=janela.destroy).pack(pady=12)

    def exportar_pdf_manual(self):
        p = filedialog.asksaveasfilename(defaultextension=".pdf")
        if not p: return
        pdf = FPDF(orientation='L', unit='mm', format='A4')
        pdf.add_page(); pdf.set_font("Arial", 'B', 11)
        pdf.cell(277, 10, "TECH PRIME PLUS - RELATÓRIO", ln=True, align='C'); pdf.ln(3)
        pdf.set_font("Arial", 'B', 7)
        headers = ["Nome", "WhatsApp", "Usuário", "Senha", "Valor", "Vencimento", "Adicionado"]
        widths  = [50,      38,         38,         38,      25,      30,            30]
        for h, w in zip(headers, widths): pdf.cell(w, 8, h, 1)
        pdf.ln()
        with self.conectar() as conn:
            for n, z, u, pw, v, d, adicionado in conn.execute("SELECT nome, whatsapp, usuario, senha, valor, vencimento, adicionado FROM clientes"):
                pdf.set_font("Arial", size=7)
                pdf.cell(50, 7, (n or "")[:25], 1)
                pdf.cell(38, 7, z or "", 1)
                pdf.cell(38, 7, (u or "")[:18], 1)
                pdf.cell(38, 7, (pw or "")[:18], 1)
                pdf.cell(25, 7, f"R$ {v:.2f}", 1)
                pdf.cell(30, 7, d or "", 1)
                pdf.cell(30, 7, adicionado or "", 1, ln=True)
        pdf.output(p); os.startfile(os.path.abspath(p))

    def exportar_excel(self):
        p = filedialog.asksaveasfilename(defaultextension=".xlsx")
        if p:
            with self.conectar() as conn:
                df = pd.read_sql_query("SELECT * FROM clientes", conn)
                df.to_excel(p, index=False); os.startfile(os.path.abspath(p))

    def janela_importar_clientes(self):
        jan = tk.Toplevel(self.root)
        jan.title("Importar Clientes do Painel")
        jan.geometry("760x680")
        jan.configure(bg="#f0f0f0")
        jan.resizable(False, False)
        jan.grab_set()
        try:
            jan.iconbitmap("logo.ico")
        except: pass
        jan.update_idletasks()
        sw = jan.winfo_screenwidth(); sh = jan.winfo_screenheight()
        jan.geometry(f"760x680+{(sw-700)//2}+{(sh-540)//2}")

        _importando = [False]  # flag para saber se importacao esta em andamento

        def fechar_janela(event=None):
            if _importando[0]:
                if messagebox.askyesno("Importação em andamento",
                        "Uma importação está em andamento!\nDeseja cancelar e fechar?", parent=jan):
                    jan.destroy()
            else:
                jan.destroy()

        jan.bind("<Escape>", fechar_janela)
        jan.protocol("WM_DELETE_WINDOW", fechar_janela)

        tk.Label(jan, text="📥 IMPORTAR CLIENTES DO PAINEL", font=("Arial", 12, "bold"),
                 bg="#f0f0f0", fg="#1a3a6c").pack(pady=(12, 2))
        tk.Label(jan, text="Suporta Excel (.xlsx), CSV (.csv) e TXT separado por | ou tabulação",
                 font=("Arial", 8, "italic"), bg="#f0f0f0", fg="#555").pack()

        # ── Mini passo a passo (compacto) ──
        frame_guia = tk.LabelFrame(jan, text=" 📋 Como Importar — Passo a Passo ",
                                   bg="#eaf4fb", padx=8, pady=3, font=("Arial", 7, "bold"),
                                   fg="#1a3a6c")
        frame_guia.pack(fill="x", padx=15, pady=(4, 2))

        passos = [
            ("1", "Prepare o arquivo:", "Excel (.xlsx), CSV ou TXT — 1ª linha = cabeçalho com nomes das colunas."),
            ("2", "Colunas aceitas:", "nome | usuario | senha | whatsapp | valor | vencimento"),
            ("3", "Selecione o arquivo:", "Clique em Abrir. O separador é detectado automaticamente."),
            ("4", "Mapeie as colunas:", "Escolha abaixo qual coluna do SEU arquivo corresponde a cada campo."),
            ("5", "Clique em IMPORTAR:", "Confira a prévia e importe. Duplicados podem ser pulados ou substituídos."),
        ]

        for num, titulo, descricao in passos:
            linha = tk.Frame(frame_guia, bg="#eaf4fb")
            linha.pack(fill="x", pady=0)
            tk.Label(linha, text=num, bg="#1a3a6c", fg="white",
                     font=("Arial", 7, "bold"), width=2).pack(side=tk.LEFT, padx=(0, 5))
            tk.Label(linha, text=titulo, bg="#eaf4fb", font=("Arial", 8, "bold"),
                     fg="#1a3a6c", width=18, anchor="w").pack(side=tk.LEFT)
            tk.Label(linha, text=descricao, bg="#eaf4fb", font=("Arial", 8),
                     fg="#333", anchor="w").pack(side=tk.LEFT)

        # ── Seleção de arquivo ──
        frame_arq = tk.Frame(jan, bg="#f0f0f0", padx=15, pady=6)
        frame_arq.pack(fill="x")
        tk.Label(frame_arq, text="Arquivo:", bg="#f0f0f0", font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        self._imp_path = tk.StringVar()
        ent_arq = ttk.Entry(frame_arq, textvariable=self._imp_path, width=55)
        ent_arq.pack(side=tk.LEFT, padx=6)

        dados_importados = []   # lista de dicts com os dados lidos

        def escolher_arquivo():
            p = filedialog.askopenfilename(
                filetypes=[("Planilha / TXT", "*.xlsx *.xls *.csv *.txt"), ("Todos", "*.*")])
            if not p:
                return
            self._imp_path.set(p)
            carregar_arquivo(p)

        ttk.Button(frame_arq, text="📂 Abrir", command=escolher_arquivo).pack(side=tk.LEFT)

        # ── Mapeamento de colunas ──
        frame_map = tk.LabelFrame(jan, text=" Mapeamento de Colunas (selecione qual coluna do arquivo corresponde a cada campo) ",
                                  bg="#f0f0f0", padx=10, pady=8, font=("Arial", 8))
        frame_map.pack(fill="x", padx=15, pady=(4, 0))

        campos_sistema = [
            ("Nome",       "nome"),
            ("Usuário",    "usuario"),
            ("Senha",      "senha"),
            ("WhatsApp",   "whatsapp"),
            ("Valor",      "valor"),
            ("Vencimento", "vencimento"),
        ]
        # Colunas do painel que mapeamos automaticamente
        AUTO_MAP = {
            # chave: possíveis nomes de coluna no arquivo (lowercase)
            "nome":       ["notas", "nome", "name", "cliente", "nota"],
            "usuario":    ["login", "usuario", "user", "username"],
            "senha":      ["senha", "password", "pass", "pw"],
            "whatsapp":   ["whatsapp", "fone", "telefone", "celular", "phone"],
            "valor":      ["valor", "preco", "price", "value"],
            "vencimento": ["vencimento", "expiry", "expiracao", "validade", "data_venc",
                           "expiration", "expires"],
        }

        combo_vars = {}
        colunas_arquivo = ["(ignorar)"]

        for i, (label, chave) in enumerate(campos_sistema):
            tk.Label(frame_map, text=label + ":", bg="#f0f0f0",
                     font=("Arial", 9), width=10, anchor="e").grid(row=i//3, column=(i%3)*2, padx=(10,2), pady=3, sticky="e")
            var = tk.StringVar(value="(ignorar)")
            cb = ttk.Combobox(frame_map, textvariable=var, values=colunas_arquivo,
                              state="readonly", width=18)
            cb.grid(row=i//3, column=(i%3)*2+1, padx=(0,10), pady=3)
            combo_vars[chave] = (var, cb)

        # ── Configurações extras ──
        frame_cfg = tk.Frame(jan, bg="#f0f0f0", padx=15, pady=2)
        frame_cfg.pack(fill="x")
        var_valor_padrao = tk.StringVar(value="0.00")
        var_dias_padrao  = tk.IntVar(value=30)
        var_zap_padrao   = tk.StringVar(value="")
        var_duplicados   = tk.StringVar(value="pular")

        tk.Label(frame_cfg, text="Valor padrão (R$):", bg="#f0f0f0", font=("Arial", 8)).pack(side=tk.LEFT)
        ttk.Entry(frame_cfg, textvariable=var_valor_padrao, width=8).pack(side=tk.LEFT, padx=(2,10))
        tk.Label(frame_cfg, text="Venc. padrão (dias):", bg="#f0f0f0", font=("Arial", 8)).pack(side=tk.LEFT)
        ttk.Entry(frame_cfg, textvariable=var_dias_padrao, width=5).pack(side=tk.LEFT, padx=(2,10))
        tk.Label(frame_cfg, text="WhatsApp padrão:", bg="#f0f0f0", font=("Arial", 8)).pack(side=tk.LEFT)
        ttk.Entry(frame_cfg, textvariable=var_zap_padrao, width=14).pack(side=tk.LEFT, padx=(2,10))
        tk.Label(frame_cfg, text="Duplicados:", bg="#f0f0f0", font=("Arial", 8)).pack(side=tk.LEFT)
        ttk.Combobox(frame_cfg, textvariable=var_duplicados,
                     values=["pular", "substituir"], state="readonly", width=10).pack(side=tk.LEFT, padx=2)

        # ── Prévia ──
        frame_prev = tk.LabelFrame(jan, text=" Prévia dos dados (primeiras 8 linhas) ",
                                   bg="#f0f0f0", padx=8, pady=6, font=("Arial", 8))
        frame_prev.pack(fill="both", expand=True, padx=15, pady=(4, 0))

        prev_tree = ttk.Treeview(frame_prev, show="headings", height=5)
        scroll_px = ttk.Scrollbar(frame_prev, orient="horizontal", command=prev_tree.xview)
        scroll_py = ttk.Scrollbar(frame_prev, orient="vertical",   command=prev_tree.yview)
        prev_tree.configure(xscrollcommand=scroll_px.set, yscrollcommand=scroll_py.set)
        scroll_py.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_px.pack(side=tk.BOTTOM, fill=tk.X)
        prev_tree.pack(fill="both", expand=True)

        self._lbl_imp_status = tk.Label(jan, text="", bg="#f0f0f0", font=("Arial", 9, "bold"), fg="#1a3a6c")
        self._lbl_imp_status.pack(pady=2)

        def carregar_arquivo(path):
            nonlocal dados_importados, colunas_arquivo
            dados_importados.clear()
            try:
                ext = os.path.splitext(path)[1].lower()
                if ext in (".xlsx", ".xls"):
                    df = pd.read_excel(path, dtype=str)
                elif ext == ".csv":
                    # Tenta detectar separador
                    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                        amostra = f.read(2048)
                    sep = ";" if amostra.count(";") > amostra.count(",") else ","
                    df = pd.read_csv(path, sep=sep, dtype=str, encoding="utf-8-sig")
                else:  # .txt — separador | ou tab
                    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                        amostra = f.read(2048)
                    sep = "|" if "|" in amostra else "\t"
                    df = pd.read_csv(path, sep=sep, dtype=str, encoding="utf-8-sig")

                df.columns = [str(c).strip() for c in df.columns]
                df = df.fillna("")
                dados_importados = df.to_dict(orient="records")
                colunas_arquivo = ["(ignorar)"] + list(df.columns)

                # Atualizar combos e fazer automapping
                for chave, (var, cb) in combo_vars.items():
                    cb["values"] = colunas_arquivo
                    var.set("(ignorar)")
                    for possivel in AUTO_MAP.get(chave, []):
                        for col in df.columns:
                            if possivel == col.lower().replace(" ", "_"):
                                var.set(col); break
                        else:
                            continue
                        break

                # Montar prévia
                for col in prev_tree["columns"]:
                    prev_tree.heading(col, text="")
                prev_tree["columns"] = list(df.columns)
                for col in df.columns:
                    prev_tree.heading(col, text=col)
                    prev_tree.column(col, width=max(80, len(col)*9), anchor="center")
                for i in prev_tree.get_children():
                    prev_tree.delete(i)
                for row in dados_importados[:8]:
                    prev_tree.insert("", "end", values=[row.get(c, "") for c in df.columns])

                self._lbl_imp_status.config(
                    text=f"✅ {len(dados_importados)} linha(s) encontrada(s) — ajuste o mapeamento e clique IMPORTAR",
                    fg="#1e5631")
            except Exception as e:
                self._lbl_imp_status.config(text=f"❌ Erro ao ler arquivo: {e}", fg="#721c24")

        def executar_importacao():
            if not dados_importados:
                messagebox.showwarning("Aviso", "Carregue um arquivo primeiro!"); return

            _importando[0] = True
            get = lambda chave: combo_vars[chave][0].get()
            ok = erros = pulados = 0
            hoje_str = datetime.now().strftime("%d/%m/%Y %H:%M")

            with self.conectar() as conn:
                for row in dados_importados:
                    try:
                        # ── campos ──
                        nome = row.get(get("nome"), "").strip() if get("nome") != "(ignorar)" else ""
                        usuario = row.get(get("usuario"), "").strip() if get("usuario") != "(ignorar)" else ""
                        senha_cli = row.get(get("senha"), "").strip() if get("senha") != "(ignorar)" else ""
                        zap = row.get(get("whatsapp"), "").strip() if get("whatsapp") != "(ignorar)" else var_zap_padrao.get().strip()
                        if not zap:
                            zap = var_zap_padrao.get().strip()

                        # Usa nome = usuario se nome vier vazio
                        if not nome:
                            nome = usuario

                        # ── valor ──
                        val_raw = row.get(get("valor"), "").strip() if get("valor") != "(ignorar)" else ""
                        try:
                            val = float(val_raw.replace(",", ".")) if val_raw else float(var_valor_padrao.get().replace(",", "."))
                        except:
                            val = float(var_valor_padrao.get().replace(",", ".") or "0")

                        # ── vencimento ──
                        venc_raw = row.get(get("vencimento"), "").strip() if get("vencimento") != "(ignorar)" else ""
                        venc_str = ""
                        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
                            try:
                                venc_str = datetime.strptime(venc_raw[:16] if len(venc_raw) > 10 else venc_raw, fmt).strftime("%d/%m/%Y")
                                break
                            except:
                                continue
                        if not venc_str:
                            venc_str = (datetime.now() + timedelta(days=var_dias_padrao.get())).strftime("%d/%m/%Y")

                        if not nome and not usuario:
                            erros += 1; continue

                        # ── duplicado ──
                        existe = conn.execute(
                            "SELECT id FROM clientes WHERE usuario=? AND usuario != ''", (usuario,)
                        ).fetchone()

                        if existe:
                            if var_duplicados.get() == "pular":
                                pulados += 1; continue
                            else:
                                conn.execute(
                                    "UPDATE clientes SET nome=?, senha=?, whatsapp=?, valor=?, vencimento=? WHERE id=?",
                                    (nome, senha_cli, zap, val, venc_str, existe[0]))
                                ok += 1
                        else:
                            conn.execute(
                                "INSERT INTO clientes (nome, whatsapp, valor, vencimento, adicionado, usuario, senha) VALUES (?,?,?,?,?,?,?)",
                                (nome, zap, val, venc_str, hoje_str, usuario, senha_cli))
                            ok += 1
                    except Exception as ex:
                        erros += 1

            conn2_msg = f"✅ {ok} importado(s)"
            if pulados: conn2_msg += f"  |  ⏭ {pulados} pulado(s)"
            if erros:   conn2_msg += f"  |  ❌ {erros} erro(s)"
            self._lbl_imp_status.config(text=conn2_msg, fg="#1e5631" if not erros else "#856404")
            self.atualizar_tudo()
            if ok:
                messagebox.showinfo("Importação concluída", conn2_msg)
                _importando[0] = False
                jan.destroy()

        # ── Botões finais ──
        frame_btns = tk.Frame(jan, bg="#f0f0f0")
        frame_btns.pack(pady=8)
        tk.Button(frame_btns, text="✅ IMPORTAR", bg="#1a3a6c", fg="white",
                  font=("Arial", 10, "bold"), relief="flat", padx=20, pady=6,
                  cursor="hand2", command=executar_importacao).pack(side=tk.LEFT, padx=8)
        tk.Button(frame_btns, text="✖ CANCELAR", bg="#f8d7da", fg="#721c24",
                  font=("Arial", 10, "bold"), relief="flat", padx=20, pady=6,
                  cursor="hand2", command=jan.destroy).pack(side=tk.LEFT, padx=8)

    def atualizar_tudo(self):
        try:
            for i in self.tab.get_children():
                self.tab.delete(i)
            if hasattr(self, 'tab2'):
                for i in self.tab2.get_children():
                    self.tab2.delete(i)
        except Exception:
            pass

        hoje = datetime.now().date()
        cont = {'tot': 0, 'atv': 0, 'vnc': 0, 'alt': 0}

        try:
            with self.conectar() as conn:
                rows = conn.execute(
                    "SELECT nome, whatsapp, usuario, senha, painel, valor, vencimento, adicionado "
                    "FROM clientes ORDER BY nome COLLATE NOCASE ASC"
                ).fetchall()
        except Exception as e:
            print(f"[atualizar_tudo] Erro banco: {e}")
            rows = []

        for row in rows:
            try:
                n   = row[0] or ""
                z   = row[1] or ""
                u   = row[2] or ""
                p   = row[3] or ""
                pnl = row[4] or ""
                v   = float(row[5]) if row[5] is not None else 0.0
                d   = row[6] or ""
                ad  = row[7] or ""
                if not d:
                    continue
                dt = datetime.strptime(d, "%d/%m/%Y").date()
                dias = (dt - hoje).days
                if dt < hoje:          tag, st = 'vencido', "Vencido"; cont['vnc'] += 1
                elif dias <= 5:        tag, st = 'alerta',  "Alerta";  cont['alt'] += 1
                else:                  tag, st = 'ativo',   "Ativo";   cont['atv'] += 1
                cont['tot'] += 1
                vals = self._row_values(n, z, u, p, pnl, v, d, ad, st)
                self.tab.insert("", "end", values=vals, tags=(tag,))
                if hasattr(self, 'tab2'):
                    self.tab2.insert("", "end", values=vals, tags=(tag,))
            except Exception:
                continue

        try:
            fat    = self.get_receita_total()
        except Exception:
            fat    = 0.0
        try:
            custos = self.get_total_custos_mes()
        except Exception:
            custos = 0.0

        liquido   = fat - custos
        icone_liq = "📈" if liquido >= 0 else "📉"

        self.c_tot.config(text=str(cont['tot']))
        self.c_atv.config(text=str(cont['atv']))
        self.c_vnc.config(text=str(cont['vnc']))
        self.c_alt.config(text=str(cont['alt']))
        self.c_fin.config(text=f"R$ {fat:.2f}".replace('.', ','))
        self.lbl_rodape.config(fg="#FFD700", text=(
            f"  👥 Clientes: {cont['tot']}    │    "
            f"✅ Ativos: {cont['atv']}    │    "
            f"⚠ A vencer: {cont['alt']}    │    "
            f"❌ Vencidos: {cont['vnc']}    │    "
            f"💰 Receita: R$ {fat:.2f}    │    "
            f"💸 Custos do mês: R$ {custos:.2f}    │    "
            f"{icone_liq} Líquido: R$ {liquido:.2f}  "
        ).replace('.', ','))
    def filtrar_por_status(self, status):
        self.ent_busca.delete(0, tk.END)
        for i in self.tab.get_children(): self.tab.delete(i)
        hoje = datetime.now().date()
        try:
            with self.conectar() as conn:
                rows = conn.execute(
                    "SELECT nome, whatsapp, usuario, senha, painel, valor, vencimento, adicionado "
                    "FROM clientes ORDER BY nome COLLATE NOCASE ASC"
                ).fetchall()
        except Exception:
            return
        for row in rows:
            try:
                n, z, u, p, pnl = row[0] or "", row[1] or "", row[2] or "", row[3] or "", row[4] or ""
                v  = float(row[5]) if row[5] is not None else 0.0
                d  = row[6] or ""
                ad = row[7] or ""
                if not d: continue
                dt = datetime.strptime(d, "%d/%m/%Y").date()
                if dt < hoje: tag, st = 'vencido', "Vencido"
                elif (dt - hoje).days <= 5: tag, st = 'alerta', "Alerta"
                else: tag, st = 'ativo', "Ativo"
                if tag != status: continue
                self.tab.insert("", "end", values=self._row_values(n, z, u, p, pnl, v, d, ad, st), tags=(tag,))
            except Exception:
                continue

    def filtrar_tabela(self):
        termo = self.ent_busca.get().strip().lower()
        for i in self.tab.get_children(): self.tab.delete(i)
        hoje = datetime.now().date()
        try:
            with self.conectar() as conn:
                rows = conn.execute(
                    "SELECT nome, whatsapp, usuario, senha, painel, valor, vencimento, adicionado "
                    "FROM clientes ORDER BY nome COLLATE NOCASE ASC"
                ).fetchall()
        except Exception:
            return
        for row in rows:
            try:
                n, z, u, p, pnl = row[0] or "", row[1] or "", row[2] or "", row[3] or "", row[4] or ""
                v  = float(row[5]) if row[5] is not None else 0.0
                d  = row[6] or ""
                ad = row[7] or ""
                if termo:
                    campos = [n.lower(), z.lower(), u.lower(), p.lower()]
                    if not any(termo in c for c in campos):
                        continue
                if not d: continue
                dt = datetime.strptime(d, "%d/%m/%Y").date()
                if dt < hoje: tag, st = 'vencido', "Vencido"
                elif (dt - hoje).days <= 5: tag, st = 'alerta', "Alerta"
                else: tag, st = 'ativo', "Ativo"
                self.tab.insert("", "end", values=self._row_values(n, z, u, p, pnl, v, d, ad, st), tags=(tag,))
            except Exception:
                continue

    def limpar_busca(self):
        self.ent_busca.delete(0, tk.END)
        self.atualizar_tudo()


    def card_estilizado(self, parent, titulo, cor, filtro=None):
        f = tk.Frame(parent, bg=cor, cursor="hand2")
        f.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        lbl_titulo = tk.Label(f, text=titulo, bg=cor, fg="white", font=('Arial', 9, 'bold'))
        lbl_titulo.pack(pady=(10, 2))
        lbl = tk.Label(f, text="0", bg=cor, fg="white", font=('Arial', 18, 'bold')); lbl.pack(pady=(0, 10))
        if filtro:
            for w in (f, lbl_titulo, lbl):
                w.bind("<Button-1>", lambda e, fi=filtro: self.filtrar_por_status(fi))
        else:
            for w in (f, lbl_titulo, lbl):
                w.bind("<Button-1>", lambda e: self.atualizar_tudo())
        return lbl

    def atualizar_relogio(self):
        agora = datetime.now()
        dias_pt = ["Segunda-feira", "Terça-feira", "Quarta-feira",
                   "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
        dia_semana = dias_pt[agora.weekday()]
        self.lbl_relogio.config(text=agora.strftime("%H:%M:%S"))
        self.lbl_data.config(text=f"{dia_semana}, {agora.strftime('%d/%m/%Y')}")
        self.root.after(1000, self.atualizar_relogio)

    def limpar_campos(self):
        self.ent_nome.delete(0, tk.END); self.ent_val.delete(0, tk.END); self.ent_zap.delete(0, tk.END)
        self.ent_usuario.delete(0, tk.END); self.ent_senha.delete(0, tk.END)
        self.ent_venc.set_date(datetime.now() + timedelta(days=30))
        self._atualizar_combo_paineis()
        self.var_painel.set("")
        self._editando_id = None

    def criar_interface_navegador(self):
        self.nav_main = tk.Frame(self.tab_nav, bg="white", padx=20, pady=20)
        self.nav_main.pack(fill="both", expand=True)
        f_cad = tk.LabelFrame(self.nav_main, text=" NOVO PAINEL DE ACESSO ", bg="white", padx=10, pady=10)
        f_cad.pack(fill="x", pady=(0, 10))
        tk.Label(f_cad, text="Nome:", bg="white").grid(row=0, column=0)
        self.link_nome = ttk.Entry(f_cad, width=15); self.link_nome.grid(row=0, column=1, padx=5)
        tk.Label(f_cad, text="URL:", bg="white").grid(row=0, column=2)
        self.link_url = ttk.Entry(f_cad, width=20); self.link_url.grid(row=0, column=3, padx=5)
        tk.Label(f_cad, text="User:", bg="white").grid(row=0, column=4)
        self.link_user = ttk.Entry(f_cad, width=12); self.link_user.grid(row=0, column=5, padx=5)
        tk.Label(f_cad, text="Senha:", bg="white").grid(row=0, column=6)
        self.link_pass = ttk.Entry(f_cad, width=12); self.link_pass.grid(row=0, column=7, padx=5)
        ttk.Button(f_cad, text="➕ SALVAR", command=self.adicionar_painel).grid(row=0, column=8, padx=5)
        ttk.Button(f_cad, text="🔄 Atualizar", command=self.renderizar_paineis).grid(row=0, column=9, padx=5)
        self.frame_cards = tk.Frame(self.nav_main, bg="white")
        self.frame_cards.pack(fill="both", expand=True)
        self.renderizar_paineis()

    def renderizar_paineis(self):
        for w in self.frame_cards.winfo_children(): w.destroy()
        with self.conectar() as conn:
            paineis = conn.execute("SELECT nome, url, usuario, senha FROM paineis").fetchall()
            for i, p in enumerate(paineis):
                nome, url, user, senha = p
                f = tk.Frame(self.frame_cards, bg="#f9f9f9", bd=1, relief="solid", padx=15, pady=15)
                f.grid(row=i//4, column=i%4, padx=10, pady=10)
                tk.Label(f, text=nome.upper(), font=('Arial', 10, 'bold'), bg="#f9f9f9", fg="#1a3a6c").pack()
                tk.Label(f, text=f"User: {user}\nPass: {senha}", font=('Arial', 8), bg="#f9f9f9").pack(pady=5)
                tk.Button(f, text="🌐 ABRIR", bg="#1a3a6c", fg="white", font=('Arial', 8, 'bold'), command=lambda u=url: webbrowser.open(u)).pack(pady=2, fill="x")
                tk.Button(f, text="✏️ EDITAR", bg="#e3f2fd", font=('Arial', 8), command=lambda d={'n':nome,'u':url,'us':user,'s':senha}: self.carregar_edicao_painel(d)).pack(pady=2, fill="x")
                tk.Button(f, text="🗑 REMOVER", bg="#721c24", fg="white", font=('Arial', 8), command=lambda n=nome: self.excluir_painel(n)).pack(pady=2, fill="x")

    def adicionar_painel(self):
        n, u, us, pw = self.link_nome.get().strip(), self.link_url.get().strip(), self.link_user.get().strip(), self.link_pass.get().strip()
        if n and u:
            with self.conectar() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM paineis WHERE nome=?", (n,))
                if cursor.fetchone(): conn.execute("UPDATE paineis SET url=?, usuario=?, senha=? WHERE nome=?", (u, us, pw, n))
                else: conn.execute("INSERT INTO paineis (nome, url, usuario, senha) VALUES (?,?,?,?)", (n, u, us, pw))
            self.renderizar_paineis(); self.link_nome.delete(0, tk.END); self.link_url.delete(0, tk.END); self.link_user.delete(0, tk.END); self.link_pass.delete(0, tk.END)

    def carregar_edicao_painel(self, d):
        self.link_nome.delete(0, tk.END); self.link_nome.insert(0, d['n'])
        self.link_url.delete(0, tk.END);  self.link_url.insert(0, d['u'])
        self.link_user.delete(0, tk.END); self.link_user.insert(0, d['us'])
        self.link_pass.delete(0, tk.END); self.link_pass.insert(0, d['s'])

    def excluir_painel(self, nome):
        if messagebox.askyesno("Excluir", f"Remover {nome}?"):
            with self.conectar() as conn: conn.execute("DELETE FROM paineis WHERE nome=?", (nome,))
            self.renderizar_paineis()

    def criar_interface_custos(self):
        main = tk.Frame(self.tab_custos, bg="#f0f0f0", padx=20, pady=15)
        main.pack(fill="both", expand=True)

        tk.Label(main, text="💸 CONTROLE DE CUSTOS", font=("Arial", 14, "bold"),
                 bg="#f0f0f0", fg="#1a3a6c").pack(pady=(0, 10))

        # ── Formulário individual ──
        form = tk.LabelFrame(main, text=" NOVO CUSTO ", bg="#d9d9d9", padx=10, pady=8)
        form.pack(fill="x", pady=(0, 5))

        tk.Label(form, text="Descrição:", bg="#d9d9d9").grid(row=0, column=0, padx=5)
        self.ent_custo_desc = ttk.Entry(form, width=30)
        self.ent_custo_desc.grid(row=0, column=1, padx=5)
        tk.Label(form, text="Valor (R$):", bg="#d9d9d9").grid(row=0, column=2, padx=5)
        self.ent_custo_val = ttk.Entry(form, width=12)
        self.ent_custo_val.grid(row=0, column=3, padx=5)
        tk.Label(form, text="Data:", bg="#d9d9d9").grid(row=0, column=4, padx=5)
        self.ent_custo_data = DateEntry(form, width=12, date_pattern="dd/mm/yyyy",
                                        background="#1a3a6c", foreground="white",
                                        borderwidth=2, locale="pt_BR")
        self.ent_custo_data.set_date(datetime.now())
        self.ent_custo_data.grid(row=0, column=5, padx=5)
        ttk.Button(form, text="➕ ADICIONAR", command=self.adicionar_custo).grid(row=0, column=6, padx=10)

        # ── Barra pesquisa + filtro data ──
        frame_filtro = tk.Frame(main, bg="#f0f0f0")
        frame_filtro.pack(fill="x", pady=(0, 4))

        tk.Label(frame_filtro, text="🔍 Pesquisar:", bg="#f0f0f0", font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        self.ent_busca_custo = ttk.Entry(frame_filtro, width=25)
        self.ent_busca_custo.pack(side=tk.LEFT, padx=(3, 10))
        self.ent_busca_custo.bind("<KeyRelease>", lambda e: self.filtrar_custos())

        tk.Label(frame_filtro, text="De:", bg="#f0f0f0", font=("Arial", 9)).pack(side=tk.LEFT)
        self.var_data_ini = tk.BooleanVar(value=False)
        tk.Checkbutton(frame_filtro, variable=self.var_data_ini, bg="#f0f0f0").pack(side=tk.LEFT)
        self.ent_data_ini = DateEntry(frame_filtro, width=11, date_pattern="dd/mm/yyyy",
                                      background="#1a3a6c", foreground="white",
                                      borderwidth=2, locale="pt_BR")
        self.ent_data_ini.pack(side=tk.LEFT, padx=3)
        # Botão para limpar a data inicial
        tk.Button(frame_filtro, text="✖", font=("Arial", 7), relief="flat", bg="#f0f0f0",
                  cursor="hand2", command=lambda: self.ent_data_ini.set_date(datetime.now())).pack(side=tk.LEFT)
        tk.Label(frame_filtro, text="Até:", bg="#f0f0f0", font=("Arial", 9)).pack(side=tk.LEFT)
        self.var_data_fim = tk.BooleanVar(value=False)
        tk.Checkbutton(frame_filtro, variable=self.var_data_fim, bg="#f0f0f0").pack(side=tk.LEFT)
        self.ent_data_fim = DateEntry(frame_filtro, width=11, date_pattern="dd/mm/yyyy",
                                      background="#1a3a6c", foreground="white",
                                      borderwidth=2, locale="pt_BR")
        self.ent_data_fim.pack(side=tk.LEFT, padx=3)
        # Botão para limpar a data final
        tk.Button(frame_filtro, text="✖", font=("Arial", 7), relief="flat", bg="#f0f0f0",
                  cursor="hand2", command=lambda: self.ent_data_fim.set_date(datetime.now())).pack(side=tk.LEFT, padx=(0,3))
        ttk.Button(frame_filtro, text="🗓 Filtrar", command=self.filtrar_custos).pack(side=tk.LEFT, padx=3)
        ttk.Button(frame_filtro, text="✖ Limpar",  command=self.limpar_filtro_custos).pack(side=tk.LEFT, padx=2)

        # ── Botões de ação ──
        frame_btns = tk.Frame(main, bg="#f0f0f0")
        frame_btns.pack(fill="x", pady=(0, 5))

        ttk.Button(frame_btns, text="✏️ EDITAR",           command=self.editar_custo).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_btns, text="🗑 EXCLUIR",           command=self.excluir_custo).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_btns, text="🗑🗑 EXCLUIR EM MASSA", command=self.excluir_custos_massa).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_btns, text="➕ ADICIONAR EM MASSA", command=self.adicionar_custos_massa).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_btns, text="📑 PDF",               command=self.exportar_pdf_custos).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_btns, text="📊 EXCEL",             command=self.exportar_excel_custos).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_btns, text="🔄 ATUALIZAR",         command=self.atualizar_custos).pack(side=tk.LEFT, padx=2)

        # ── Resumo ──
        self.lbl_resumo_custos = tk.Label(main, text="", bg="#1a3a6c", fg="white",
                                           font=("Arial", 10, "bold"), padx=15, pady=8)
        self.lbl_resumo_custos.pack(fill="x", pady=(0, 5))

        # ── Tabela ──
        frame_tab = tk.Frame(main)
        frame_tab.pack(fill="both", expand=True)
        scroll_y = ttk.Scrollbar(frame_tab, orient="vertical")
        scroll_x = ttk.Scrollbar(frame_tab, orient="horizontal")
        self.tab_custos_tree = ttk.Treeview(frame_tab, columns=["ID", "DESC", "VAL", "DATA"],
                                             show="headings", yscrollcommand=scroll_y.set,
                                             xscrollcommand=scroll_x.set, selectmode="extended")
        scroll_y.config(command=self.tab_custos_tree.yview)
        scroll_x.config(command=self.tab_custos_tree.xview)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.tab_custos_tree.pack(fill="both", expand=True)

        self.tab_custos_tree.heading("ID",   text="ID");          self.tab_custos_tree.column("ID",   width=50,  anchor="center")
        self.tab_custos_tree.heading("DESC", text="Descrição");   self.tab_custos_tree.column("DESC", width=400)
        self.tab_custos_tree.heading("VAL",  text="Valor");       self.tab_custos_tree.column("VAL",  width=120, anchor="center")
        self.tab_custos_tree.heading("DATA", text="Data");        self.tab_custos_tree.column("DATA", width=120, anchor="center")

        self.atualizar_custos()

    def adicionar_custo(self):
        desc = self.ent_custo_desc.get().strip()
        val_raw = self.ent_custo_val.get().strip()
        data = self.ent_custo_data.get().strip()
        if not desc or not val_raw:
            messagebox.showwarning("Aviso", "Preencha descrição e valor!"); return
        try:
            val = float(val_raw.replace(',', '.'))
            with self.conectar() as conn:
                conn.execute("INSERT INTO custos (descricao, valor, data) VALUES (?,?,?)", (desc, val, data))
            self.ent_custo_desc.delete(0, tk.END)
            self.ent_custo_val.delete(0, tk.END)
            self.ent_custo_data.set_date(datetime.now())
            self.atualizar_custos(); self.atualizar_tudo()
        except:
            messagebox.showerror("Erro", "Valor inválido!")

    def editar_custo(self):
        sel = self.tab_custos_tree.selection()
        if not sel: messagebox.showwarning("Aviso", "Selecione um custo para editar!"); return
        vals = self.tab_custos_tree.item(sel[0])['values']
        cid, desc_atual, val_atual, data_atual = vals[0], vals[1], str(vals[2]).replace('R$ ', '').replace(',', '.'), vals[3]

        jan = tk.Toplevel(self.root); jan.title("Editar Custo"); jan.geometry("400x200")
        jan.configure(bg="#f0f0f0"); jan.resizable(False, False); jan.grab_set()

        tk.Label(jan, text="Descrição:", bg="#f0f0f0").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        ent_d = ttk.Entry(jan, width=30); ent_d.insert(0, desc_atual); ent_d.grid(row=0, column=1, padx=10)
        tk.Label(jan, text="Valor (R$):", bg="#f0f0f0").grid(row=1, column=0, padx=10, pady=8, sticky="w")
        ent_v = ttk.Entry(jan, width=30); ent_v.insert(0, val_atual); ent_v.grid(row=1, column=1, padx=10)
        tk.Label(jan, text="Data:", bg="#f0f0f0").grid(row=2, column=0, padx=10, pady=8, sticky="w")
        ent_dt = ttk.Entry(jan, width=30); ent_dt.insert(0, data_atual); ent_dt.grid(row=2, column=1, padx=10)

        def salvar():
            try:
                val = float(ent_v.get().strip().replace(',', '.'))
                with self.conectar() as conn:
                    conn.execute("UPDATE custos SET descricao=?, valor=?, data=? WHERE id=?",
                                 (ent_d.get().strip(), val, ent_dt.get().strip(), cid))
                jan.destroy(); self.atualizar_custos(); self.atualizar_tudo()
            except: messagebox.showerror("Erro", "Valor inválido!")

        ttk.Button(jan, text="💾 SALVAR", command=salvar).grid(row=3, column=0, columnspan=2, pady=15)

    def excluir_custo(self):
        sel = self.tab_custos_tree.selection()
        if not sel: return
        cid = self.tab_custos_tree.item(sel[0])['values'][0]
        if messagebox.askyesno("Excluir", "Remover este custo?"):
            with self.conectar() as conn:
                conn.execute("DELETE FROM custos WHERE id=?", (cid,))
            self.atualizar_custos(); self.atualizar_tudo()

    def excluir_custos_massa(self):
        sel = self.tab_custos_tree.selection()
        if not sel: messagebox.showwarning("Aviso", "Selecione um ou mais custos!"); return
        if not messagebox.askyesno("Excluir em massa", f"Remover {len(sel)} custo(s) selecionado(s)?"): return
        ids = [self.tab_custos_tree.item(s)['values'][0] for s in sel]
        with self.conectar() as conn:
            for cid in ids: conn.execute("DELETE FROM custos WHERE id=?", (cid,))
        self.atualizar_custos(); self.atualizar_tudo()

    def adicionar_custos_massa(self):
        jan = tk.Toplevel(self.root); jan.title("Adicionar Custos em Massa")
        jan.geometry("520x400"); jan.configure(bg="#f0f0f0"); jan.grab_set()

        tk.Label(jan, text="Digite um custo por linha no formato:  Descrição | Valor | Data (dd/mm/aaaa)",
                 bg="#f0f0f0", font=("Arial", 8, "italic"), fg="#555").pack(pady=(10,2), padx=10, anchor="w")
        tk.Label(jan, text="Exemplo:  Servidor VPS | 150,00 | 15/04/2026",
                 bg="#f0f0f0", font=("Arial", 8, "italic"), fg="#1a3a6c").pack(padx=10, anchor="w")

        txt = tk.Text(jan, height=15, font=("Consolas", 10), relief="solid", bd=1)
        txt.pack(fill="both", expand=True, padx=10, pady=8)

        def importar():
            linhas = txt.get("1.0", "end-1c").strip().split("\n")
            ok, erros = 0, []
            with self.conectar() as conn:
                for i, linha in enumerate(linhas, 1):
                    if not linha.strip(): continue
                    partes = [p.strip() for p in linha.split("|")]
                    if len(partes) < 2: erros.append(f"Linha {i}: formato inválido"); continue
                    try:
                        desc = partes[0]
                        val = float(partes[1].replace(',', '.'))
                        data = partes[2] if len(partes) >= 3 else datetime.now().strftime("%d/%m/%Y")
                        conn.execute("INSERT INTO custos (descricao, valor, data) VALUES (?,?,?)", (desc, val, data))
                        ok += 1
                    except: erros.append(f"Linha {i}: erro ao processar")
            self.atualizar_custos(); self.atualizar_tudo()
            msg = f"{ok} custo(s) importado(s) com sucesso!"
            if erros: msg += "\n\nErros:\n" + "\n".join(erros)
            messagebox.showinfo("Resultado", msg); jan.destroy()

        ttk.Button(jan, text="✅ IMPORTAR TUDO", command=importar).pack(pady=5)

    def exportar_pdf_custos(self):
        p = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile="custos.pdf")
        if not p: return
        pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", 'B', 12)
        pdf.cell(190, 10, "TECH PRIME PLUS - RELATÓRIO DE CUSTOS", ln=True, align='C'); pdf.ln(5)
        pdf.set_font("Arial", 'B', 9)
        for h, w in zip(["Descrição", "Valor", "Data"], [110, 40, 40]): pdf.cell(w, 8, h, 1)
        pdf.ln()
        with self.conectar() as conn:
            for _, desc, val, data in conn.execute("SELECT id, descricao, valor, data FROM custos ORDER BY data DESC"):
                pdf.set_font("Arial", size=8)
                pdf.cell(110, 7, (desc or "")[:50], 1)
                pdf.cell(40,  7, f"R$ {val:.2f}", 1)
                pdf.cell(40,  7, data or "", 1, ln=True)
        pdf.output(p); os.startfile(os.path.abspath(p))

    def exportar_excel_custos(self):
        p = filedialog.asksaveasfilename(defaultextension=".xlsx", initialfile="custos.xlsx")
        if p:
            with self.conectar() as conn:
                df = pd.read_sql_query("SELECT descricao, valor, data FROM custos ORDER BY data DESC", conn)
                df.to_excel(p, index=False); os.startfile(os.path.abspath(p))

    def filtrar_custos(self):
        termo = self.ent_busca_custo.get().strip().lower()
        usar_ini = self.var_data_ini.get()
        usar_fim = self.var_data_fim.get()
        data_ini = self.ent_data_ini.get().strip() if usar_ini else ""
        data_fim = self.ent_data_fim.get().strip() if usar_fim else ""
        for i in self.tab_custos_tree.get_children(): self.tab_custos_tree.delete(i)
        hoje = datetime.now()
        mes_atual = hoje.strftime("%m/%Y")
        total_mes = 0.0
        with self.conectar() as conn:
            for cid, desc, val, data in conn.execute("SELECT id, descricao, valor, data FROM custos ORDER BY data DESC"):
                if termo and termo not in (desc or "").lower(): continue
                if data_ini or data_fim:
                    try:
                        dt = datetime.strptime(data, "%d/%m/%Y")
                        if data_ini:
                            di = datetime.strptime(data_ini, "%d/%m/%Y")
                            if dt < di: continue
                        if data_fim:
                            df = datetime.strptime(data_fim, "%d/%m/%Y")
                            if dt > df: continue
                    except: pass
                self.tab_custos_tree.insert("", "end", values=(cid, desc, f"R$ {val:.2f}", data or ""))
                if data and data[3:] == mes_atual:
                    total_mes += val
        fat = self.get_receita_total()
        liquido = fat - total_mes
        self.lbl_resumo_custos.config(
            text=f"  Receita do mês: R$ {fat:.2f}   |   Custos filtrados: R$ {total_mes:.2f}   |   Líquido: R$ {liquido:.2f}  ".replace('.', ','))


    def limpar_filtro_custos(self):
        self.ent_busca_custo.delete(0, tk.END)
        self.var_data_ini.set(False)
        self.var_data_fim.set(False)
        self.ent_data_ini.set_date(datetime.now())
        self.ent_data_fim.set_date(datetime.now())
        self.atualizar_custos()

    def atualizar_custos(self):
        if not self._aba_construida.get('custos'):
            return
        for i in self.tab_custos_tree.get_children(): self.tab_custos_tree.delete(i)
        hoje = datetime.now()
        mes_atual = hoje.strftime("%m/%Y")
        total_mes = 0.0
        with self.conectar() as conn:
            for cid, desc, val, data in conn.execute("SELECT id, descricao, valor, data FROM custos ORDER BY data DESC"):
                self.tab_custos_tree.insert("", "end", values=(cid, desc, f"R$ {val:.2f}", data or ""))
                if data and data[3:] == mes_atual:
                    total_mes += val
        fat = self.get_receita_total()
        liquido = fat - total_mes
        self.lbl_resumo_custos.config(
            text=f"  Receita do mês: R$ {fat:.2f}   |   Custos do mês: R$ {total_mes:.2f}   |   Líquido: R$ {liquido:.2f}  ".replace('.', ',')
        )

    def criar_interface_logs(self):
        main = tk.Frame(self.tab_logs, bg="#f0f0f0", padx=20, pady=15)
        main.pack(fill="both", expand=True)

        tk.Label(main, text="📋 LOGS DO SISTEMA", font=("Arial", 14, "bold"),
                 bg="#f0f0f0", fg="#1a3a6c").pack(pady=(0, 8))

        # ── Barra de filtros ──
        frame_filtros = tk.LabelFrame(main, text=" Filtros ", bg="#f0f0f0",
                                      padx=10, pady=8, font=("Arial", 9, "bold"))
        frame_filtros.pack(fill="x", pady=(0, 6))

        linha1 = tk.Frame(frame_filtros, bg="#f0f0f0")
        linha1.pack(fill="x", pady=(0, 4))

        # Pesquisa por texto
        tk.Label(linha1, text="🔍 Pesquisar:", bg="#f0f0f0", font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        self.ent_busca_log = ttk.Entry(linha1, width=30, font=("Arial", 10))
        self.ent_busca_log.pack(side=tk.LEFT, padx=(4, 12))
        self.ent_busca_log.bind("<KeyRelease>", lambda e: self.filtrar_logs())

        # Filtro por tipo
        tk.Label(linha1, text="Tipo:", bg="#f0f0f0", font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        self.var_filtro_tipo_log = tk.StringVar(value="Todos")
        self.cmb_tipo_log = ttk.Combobox(linha1, textvariable=self.var_filtro_tipo_log,
                                          values=["Todos", "CADASTRO", "EDIÇÃO", "EXCLUSÃO",
                                                  "EXCLUSÃO AUTO", "RENOVAÇÃO",
                                                  "WPP ENVIADO", "AVISO VENCIDO"],
                                          state="readonly", width=16)
        self.cmb_tipo_log.pack(side=tk.LEFT, padx=(4, 12))
        self.cmb_tipo_log.bind("<<ComboboxSelected>>", lambda e: self.filtrar_logs())

        # Filtro por usuário
        tk.Label(linha1, text="Usuário:", bg="#f0f0f0", font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        self.ent_filtro_usuario_log = ttk.Entry(linha1, width=14, font=("Arial", 10))
        self.ent_filtro_usuario_log.pack(side=tk.LEFT, padx=(4, 12))
        self.ent_filtro_usuario_log.bind("<KeyRelease>", lambda e: self.filtrar_logs())

        linha2 = tk.Frame(frame_filtros, bg="#f0f0f0")
        linha2.pack(fill="x")

        # Filtro por data
        tk.Label(linha2, text="De:", bg="#f0f0f0", font=("Arial", 9)).pack(side=tk.LEFT)
        self.var_log_data_ini = tk.BooleanVar(value=False)
        tk.Checkbutton(linha2, variable=self.var_log_data_ini, bg="#f0f0f0").pack(side=tk.LEFT)
        self.ent_log_data_ini = DateEntry(linha2, width=11, date_pattern="dd/mm/yyyy",
                                           background="#1a3a6c", foreground="white",
                                           borderwidth=2, locale="pt_BR")
        self.ent_log_data_ini.pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(linha2, text="Até:", bg="#f0f0f0", font=("Arial", 9)).pack(side=tk.LEFT)
        self.var_log_data_fim = tk.BooleanVar(value=False)
        tk.Checkbutton(linha2, variable=self.var_log_data_fim, bg="#f0f0f0").pack(side=tk.LEFT)
        self.ent_log_data_fim = DateEntry(linha2, width=11, date_pattern="dd/mm/yyyy",
                                           background="#1a3a6c", foreground="white",
                                           borderwidth=2, locale="pt_BR")
        self.ent_log_data_fim.pack(side=tk.LEFT, padx=(0, 12))

        ttk.Button(linha2, text="🗓 Filtrar", command=self.filtrar_logs).pack(side=tk.LEFT, padx=2)
        ttk.Button(linha2, text="✖ Limpar", command=self.limpar_filtro_logs).pack(side=tk.LEFT, padx=2)

        # ── Botões de ação ──
        frame_btns = tk.Frame(main, bg="#f0f0f0")
        frame_btns.pack(fill="x", pady=(0, 6))
        ttk.Button(frame_btns, text="🔄 Atualizar",   command=self.atualizar_logs).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_btns, text="🗑 Limpar Logs", command=self.limpar_logs).pack(side=tk.LEFT, padx=2)

        # Contador de logs
        self.lbl_total_logs = tk.Label(frame_btns, text="", bg="#f0f0f0",
                                        fg="#1a3a6c", font=("Arial", 9, "bold"))
        self.lbl_total_logs.pack(side=tk.RIGHT, padx=8)

        # ── Tabela ──
        frame_tab = tk.Frame(main)
        frame_tab.pack(fill="both", expand=True)
        scroll_y = ttk.Scrollbar(frame_tab, orient="vertical")
        scroll_x = ttk.Scrollbar(frame_tab, orient="horizontal")
        self.tab_logs_tree = ttk.Treeview(
            frame_tab,
            columns=["ID", "TIPO", "DESC", "USUARIO", "DATA"],
            show="headings",
            yscrollcommand=scroll_y.set,
            xscrollcommand=scroll_x.set
        )
        scroll_y.config(command=self.tab_logs_tree.yview)
        scroll_x.config(command=self.tab_logs_tree.xview)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.tab_logs_tree.pack(fill="both", expand=True)

        self.tab_logs_tree.heading("ID",      text="#");          self.tab_logs_tree.column("ID",      width=40,  anchor="center")
        self.tab_logs_tree.heading("TIPO",    text="Tipo");       self.tab_logs_tree.column("TIPO",    width=120, anchor="center")
        self.tab_logs_tree.heading("DESC",    text="Descrição");  self.tab_logs_tree.column("DESC",    width=440)
        self.tab_logs_tree.heading("USUARIO", text="Usuário");    self.tab_logs_tree.column("USUARIO", width=110, anchor="center")
        self.tab_logs_tree.heading("DATA",    text="Data/Hora");  self.tab_logs_tree.column("DATA",    width=140, anchor="center")

        self.tab_logs_tree.tag_configure("CADASTRO",      background="#e7f3ec")
        self.tab_logs_tree.tag_configure("EDIÇÃO",        background="#e3f2fd")
        self.tab_logs_tree.tag_configure("EXCLUSÃO",      background="#f8d7da")
        self.tab_logs_tree.tag_configure("EXCLUSÃO AUTO", background="#fff3cd")
        self.tab_logs_tree.tag_configure("RENOVAÇÃO",     background="#f3e5f5")
        self.tab_logs_tree.tag_configure("WPP ENVIADO",   background="#e0f7e9")
        self.tab_logs_tree.tag_configure("AVISO VENCIDO", background="#fde8d8")

        self.atualizar_logs()

    def filtrar_logs(self):
        termo = self.ent_busca_log.get().strip().lower()
        tipo_sel = self.var_filtro_tipo_log.get()
        usuario_sel = self.ent_filtro_usuario_log.get().strip().lower()
        usar_ini = self.var_log_data_ini.get()
        usar_fim = self.var_log_data_fim.get()
        data_ini = self.ent_log_data_ini.get().strip() if usar_ini else ""
        data_fim = self.ent_log_data_fim.get().strip() if usar_fim else ""

        for i in self.tab_logs_tree.get_children():
            self.tab_logs_tree.delete(i)

        count = 0
        with self.conectar() as conn:
            try:
                rows = conn.execute(
                    "SELECT id, tipo, descricao, COALESCE(usuario,''), data FROM logs ORDER BY id DESC"
                ).fetchall()
            except:
                rows = conn.execute(
                    "SELECT id, tipo, descricao, '' as usuario, data FROM logs ORDER BY id DESC"
                ).fetchall()

        for lid, tipo, desc, usuario, data in rows:
            # Filtro tipo
            if tipo_sel != "Todos" and tipo != tipo_sel:
                continue
            # Filtro texto
            if termo and termo not in (desc or "").lower() and termo not in (tipo or "").lower():
                continue
            # Filtro usuário
            if usuario_sel and usuario_sel not in (usuario or "").lower():
                continue
            # Filtro data
            if data_ini or data_fim:
                try:
                    dt_str = data[:10] if data else ""
                    dt = datetime.strptime(dt_str, "%d/%m/%Y")
                    if data_ini:
                        di = datetime.strptime(data_ini, "%d/%m/%Y")
                        if dt < di: continue
                    if data_fim:
                        df_d = datetime.strptime(data_fim, "%d/%m/%Y")
                        if dt > df_d: continue
                except:
                    pass
            tag = tipo if tipo in ("CADASTRO", "EDIÇÃO", "EXCLUSÃO", "EXCLUSÃO AUTO",
                                   "RENOVAÇÃO", "WPP ENVIADO", "AVISO VENCIDO") else ""
            self.tab_logs_tree.insert("", "end",
                                       values=(lid, tipo, desc, usuario, data),
                                       tags=(tag,))
            count += 1
        self.lbl_total_logs.config(text=f"Total: {count} log(s)")

    def limpar_filtro_logs(self):
        self.ent_busca_log.delete(0, tk.END)
        self.var_filtro_tipo_log.set("Todos")
        self.ent_filtro_usuario_log.delete(0, tk.END)
        self.var_log_data_ini.set(False)
        self.var_log_data_fim.set(False)
        self.atualizar_logs()

    def atualizar_logs(self):
        if not self._aba_construida.get('logs'):
            return
        for i in self.tab_logs_tree.get_children():
            self.tab_logs_tree.delete(i)
        count = 0
        with self.conectar() as conn:
            try:
                rows = conn.execute(
                    "SELECT id, tipo, descricao, COALESCE(usuario,''), data FROM logs ORDER BY id DESC"
                ).fetchall()
            except:
                rows = conn.execute(
                    "SELECT id, tipo, descricao, '' as usuario, data FROM logs ORDER BY id DESC"
                ).fetchall()
        for lid, tipo, desc, usuario, data in rows:
            tag = tipo if tipo in ("CADASTRO", "EDIÇÃO", "EXCLUSÃO", "EXCLUSÃO AUTO",
                                   "RENOVAÇÃO", "WPP ENVIADO", "AVISO VENCIDO") else ""
            self.tab_logs_tree.insert("", "end",
                                       values=(lid, tipo, desc, usuario, data),
                                       tags=(tag,))
            count += 1
        if hasattr(self, 'lbl_total_logs'):
            self.lbl_total_logs.config(text=f"Total: {count} log(s)")

    def limpar_logs(self):
        if messagebox.askyesno("Limpar", "Apagar todo o histórico de logs?"):
            with self.conectar() as conn: conn.execute("DELETE FROM logs")
            self.atualizar_logs()

    def criar_interface_config(self):
        # Canvas + scrollbar para a aba de configurações
        canvas = tk.Canvas(self.tab_config, bg="#f0f0f0", highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.tab_config, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill="both", expand=True)

        frame = tk.Frame(canvas, bg="#f0f0f0", padx=40, pady=20)
        frame_id = canvas.create_window((0, 0), window=frame, anchor="nw")

        def on_resize(event):
            canvas.itemconfig(frame_id, width=event.width)
        canvas.bind("<Configure>", on_resize)

        def on_frame_change(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        frame.bind("<Configure>", on_frame_change)

        # Scroll com roda do mouse
        def _scroll(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _scroll)

        tk.Label(frame, text="⚙️ CONFIGURAÇÕES DO SISTEMA", font=("Arial", 14, "bold"),
                 bg="#f0f0f0", fg="#1a3a6c").pack(pady=(0, 20))

        # ── Backup & Restauração ──────────────────────────────────────────────
        box_bak = tk.LabelFrame(frame, text=" 🛡️ Backup & Restauração ",
                                bg="#f0f0f0", padx=20, pady=16, font=("Arial", 10, "bold"))
        box_bak.pack(fill="x", pady=(0, 20))

        tk.Label(box_bak,
                 text="Crie backups manuais do banco de dados ou restaure a partir de um arquivo .db anterior.",
                 bg="#f0f0f0", font=("Arial", 9)).pack(anchor="w", pady=(0, 6))

        # ── Linha de backup manual ──
        frm_bak = tk.Frame(box_bak, bg="#f0f0f0")
        frm_bak.pack(fill="x", pady=(0, 8))

        tk.Button(frm_bak, text="💾 FAZER BACKUP AGORA", bg="#1a3a6c", fg="white",
                  font=("Arial", 9, "bold"), relief="flat", padx=12, pady=6,
                  cursor="hand2", command=self.fazer_backup_manual).pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(frm_bak,
                 text="Salva uma cópia do banco em local escolhido por você.",
                 bg="#f0f0f0", fg="#555", font=("Arial", 8, "italic")).pack(side=tk.LEFT)

        ttk.Separator(box_bak, orient="horizontal").pack(fill="x", pady=(4, 12))

        # ── Restauração ──
        tk.Label(box_bak, text="Restaurar Backup:", bg="#f0f0f0",
                 font=("Arial", 10, "bold"), fg="#721c24").pack(anchor="w")
        tk.Label(box_bak,
                 text="⚠ ATENÇÃO: restaurar substitui TODOS os dados atuais pelo conteúdo do backup selecionado. "
                      "Esta ação não pode ser desfeita.",
                 bg="#fff3cd", fg="#856404", font=("Arial", 8, "italic"),
                 wraplength=660, justify="left", padx=8, pady=5,
                 relief="solid", bd=1).pack(fill="x", pady=(4, 10))

        frm_rest = tk.Frame(box_bak, bg="#f0f0f0")
        frm_rest.pack(fill="x")

        # Campo que mostra o arquivo selecionado
        var_bak_path = tk.StringVar(value="Nenhum arquivo selecionado")
        lbl_bak_arquivo = tk.Label(frm_rest, textvariable=var_bak_path,
                                    bg="#f5f5f5", fg="#333", font=("Arial", 9),
                                    relief="sunken", bd=1, anchor="w", padx=8,
                                    width=55)
        lbl_bak_arquivo.pack(side=tk.LEFT, padx=(0, 8), ipady=4)

        def escolher_backup():
            pasta_auto = "backups_automaticos"
            inicial = pasta_auto if os.path.exists(pasta_auto) else "."
            p = filedialog.askopenfilename(
                title="Selecione o arquivo de backup",
                initialdir=inicial,
                filetypes=[("Banco de dados", "*.db"), ("Todos os arquivos", "*.*")]
            )
            if p:
                var_bak_path.set(p)
                btn_restaurar.config(state="normal")

        def restaurar_backup():
            caminho = var_bak_path.get()
            if not caminho or caminho == "Nenhum arquivo selecionado":
                messagebox.showwarning("Aviso", "Selecione um arquivo de backup primeiro!"); return
            if not os.path.exists(caminho):
                messagebox.showerror("Erro", f"Arquivo não encontrado:\n{caminho}"); return

            # Confirmação dupla — ação destrutiva
            if not messagebox.askyesno("Confirmar Restauração",
                    f"Tem certeza que deseja restaurar o banco a partir de:\n\n{caminho}\n\n"
                    "TODOS os dados atuais serão substituídos!"):
                return
            if not messagebox.askyesno("Confirmação Final",
                    "⚠ Esta é sua última chance!\n\n"
                    "Confirma a restauração? Os dados atuais serão perdidos."):
                return

            try:
                # Faz backup de segurança dos dados atuais antes de restaurar
                seguranca = f"pre_restauracao_{datetime.now().strftime('%d_%m_%Y_%H%M%S')}.db"
                pasta_seg = "backups_automaticos"
                if not os.path.exists(pasta_seg):
                    os.makedirs(pasta_seg)
                shutil.copy2(self.db_file, os.path.join(pasta_seg, seguranca))

                # Restaura o backup selecionado
                shutil.copy2(caminho, self.db_file)

                messagebox.showinfo("✅ Restauração concluída",
                    f"Banco restaurado com sucesso!\n\n"
                    f"Uma cópia de segurança dos dados anteriores foi salva em:\n"
                    f"{pasta_seg}/{seguranca}\n\n"
                    "Reinicie o sistema para garantir que todas as telas sejam atualizadas.")

                var_bak_path.set("Nenhum arquivo selecionado")
                btn_restaurar.config(state="disabled")
                self.atualizar_tudo()

            except Exception as e:
                messagebox.showerror("Erro na restauração", f"Falha ao restaurar:\n{e}")

        # Listar backups automáticos disponíveis
        def listar_backups():
            pasta = "backups_automaticos"
            if not os.path.exists(pasta):
                messagebox.showinfo("Backups automáticos",
                    "Nenhum backup automático encontrado.\n"
                    "Os backups automáticos são criados em 'backups_automaticos/' a cada cadastro."); return
            arquivos = sorted(
                [f for f in os.listdir(pasta) if f.endswith(".db")],
                reverse=True
            )
            if not arquivos:
                messagebox.showinfo("Backups automáticos", "Nenhum arquivo .db encontrado na pasta de backups."); return

            jan_list = tk.Toplevel(frame.winfo_toplevel())
            jan_list.title("📂 Backups Disponíveis")
            jan_list.geometry("560x380")
            jan_list.configure(bg="#f0f0f0")
            jan_list.resizable(False, False)
            jan_list.grab_set()
            jan_list.update_idletasks()
            sw = jan_list.winfo_screenwidth(); sh = jan_list.winfo_screenheight()
            jan_list.geometry(f"560x380+{(sw-560)//2}+{(sh-380)//2}")

            tk.Label(jan_list, text="📂 BACKUPS AUTOMÁTICOS DISPONÍVEIS",
                     font=("Arial", 11, "bold"), bg="#f0f0f0", fg="#1a3a6c").pack(pady=(14, 6))
            tk.Label(jan_list, text=f"Pasta: {os.path.abspath(pasta)}",
                     font=("Arial", 8, "italic"), bg="#f0f0f0", fg="#555").pack()

            frame_lst = tk.Frame(jan_list); frame_lst.pack(fill="both", expand=True, padx=14, pady=8)
            sb = ttk.Scrollbar(frame_lst, orient="vertical")
            lst = tk.Listbox(frame_lst, font=("Consolas", 9), yscrollcommand=sb.set,
                             selectmode="single", bg="white", bd=1, relief="solid",
                             activestyle="dotbox")
            sb.config(command=lst.yview)
            sb.pack(side=tk.RIGHT, fill=tk.Y)
            lst.pack(fill="both", expand=True)

            for arq in arquivos:
                tamanho = os.path.getsize(os.path.join(pasta, arq))
                lst.insert(tk.END, f"  {arq}   ({tamanho/1024:.1f} KB)")

            def selecionar():
                sel_idx = lst.curselection()
                if not sel_idx:
                    messagebox.showwarning("Aviso", "Selecione um arquivo!", parent=jan_list); return
                nome_arq = arquivos[sel_idx[0]]
                caminho_sel = os.path.join(pasta, nome_arq)
                var_bak_path.set(caminho_sel)
                btn_restaurar.config(state="normal")
                jan_list.destroy()

            frm_btns_lst = tk.Frame(jan_list, bg="#f0f0f0"); frm_btns_lst.pack(pady=8)
            tk.Button(frm_btns_lst, text="✅ USAR ESTE BACKUP", bg="#1a3a6c", fg="white",
                      font=("Arial", 9, "bold"), relief="flat", padx=12, pady=6,
                      cursor="hand2", command=selecionar).pack(side=tk.LEFT, padx=6)
            tk.Button(frm_btns_lst, text="✖ Cancelar", bg="#f8d7da", fg="#721c24",
                      font=("Arial", 9, "bold"), relief="flat", padx=12, pady=6,
                      cursor="hand2", command=jan_list.destroy).pack(side=tk.LEFT, padx=6)

        frm_rest_btns = tk.Frame(box_bak, bg="#f0f0f0")
        frm_rest_btns.pack(anchor="w", pady=(8, 0))

        tk.Button(frm_rest_btns, text="📂 Selecionar Arquivo", bg="#374151", fg="white",
                  font=("Arial", 9, "bold"), relief="flat", padx=10, pady=6,
                  cursor="hand2", command=escolher_backup).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(frm_rest_btns, text="📋 Ver Backups Automáticos", bg="#856404", fg="white",
                  font=("Arial", 9, "bold"), relief="flat", padx=10, pady=6,
                  cursor="hand2", command=listar_backups).pack(side=tk.LEFT, padx=6)
        btn_restaurar = tk.Button(frm_rest_btns, text="♻️ RESTAURAR BACKUP", bg="#721c24", fg="white",
                                   font=("Arial", 9, "bold"), relief="flat", padx=10, pady=6,
                                   cursor="hand2", command=restaurar_backup, state="disabled")
        btn_restaurar.pack(side=tk.LEFT, padx=6)

        tk.Label(box_bak,
                 text="💡 Dica: backups automáticos ficam em 'backups_automaticos/' na pasta do sistema.",
                 bg="#f0f0f0", fg="#555", font=("Arial", 8, "italic")).pack(anchor="w", pady=(10, 0))

        # ── Nome da Empresa ──
        box = tk.LabelFrame(frame, text=" Nome da Empresa ", bg="#f0f0f0", padx=20, pady=20, font=("Arial", 10, "bold"))
        box.pack(fill="x", pady=(0, 20))

        tk.Label(box, text="Este nome aparece na mensagem enviada pelo WhatsApp:", bg="#f0f0f0", font=("Arial", 9)).pack(anchor="w")
        tk.Label(box, text='Ex: "Olá João, seu acesso aos canais [NOME DA EMPRESA] vence em..."',
                 bg="#f0f0f0", font=("Arial", 8, "italic"), fg="#555").pack(anchor="w", pady=(0, 10))

        ent_frame = tk.Frame(box, bg="#f0f0f0")
        ent_frame.pack(anchor="w")
        self.ent_empresa = ttk.Entry(ent_frame, width=35, font=("Arial", 11))
        self.ent_empresa.insert(0, self.get_nome_empresa())
        self.ent_empresa.pack(side=tk.LEFT, padx=(0, 10))

        def salvar_config():
            nome = self.ent_empresa.get().strip()
            if not nome:
                messagebox.showwarning("Aviso", "Informe o nome da empresa!"); return
            self.salvar_nome_empresa(nome)
            messagebox.showinfo("Sucesso", f"Nome da empresa salvo como: {nome}")

        ttk.Button(ent_frame, text="💾 SALVAR", command=salvar_config).pack(side=tk.LEFT)

        # ── Mensagem do WhatsApp ──
        box_msg = tk.LabelFrame(frame, text=" Mensagem do WhatsApp ", bg="#f0f0f0", padx=20, pady=20, font=("Arial", 10, "bold"))
        box_msg.pack(fill="x", pady=(0, 20))

        tk.Label(box_msg, text="Personalize o texto enviado pelo botão WhatsApp.", bg="#f0f0f0", font=("Arial", 9)).pack(anchor="w")
        tk.Label(box_msg, text="Variáveis disponíveis:  {nome}  |  {empresa}  |  {vencimento}",
                 bg="#f0f0f0", font=("Arial", 8, "italic"), fg="#1a3a6c").pack(anchor="w", pady=(2, 8))

        self.txt_msg_zap = tk.Text(box_msg, height=4, width=80, font=("Arial", 10), wrap="word",
                                    relief="solid", bd=1)
        self.txt_msg_zap.insert("1.0", self.get_mensagem_whatsapp())
        self.txt_msg_zap.pack(fill="x", pady=(0, 8))

        preview_frame = tk.Frame(box_msg, bg="#f0f0f0")
        preview_frame.pack(fill="x")

        lbl_preview = tk.Label(box_msg, text="", bg="#fff3cd", fg="#856404", font=("Arial", 8, "italic"),
                                wraplength=700, justify="left", padx=8, pady=5, relief="solid", bd=1)
        lbl_preview.pack(fill="x", pady=(0, 8))

        def atualizar_preview(*args):
            t = self.txt_msg_zap.get("1.0", "end-1c")
            preview = t.replace("{nome}", "João Silva").replace("{empresa}", self.get_nome_empresa()).replace("{vencimento}", "30/04/2026")
            lbl_preview.config(text="Prévia: " + preview)

        self.txt_msg_zap.bind("<KeyRelease>", atualizar_preview)
        atualizar_preview()

        def salvar_mensagem():
            msg = self.txt_msg_zap.get("1.0", "end-1c").strip()
            if not msg:
                messagebox.showwarning("Aviso", "A mensagem não pode estar vazia!"); return
            self.salvar_mensagem_whatsapp(msg)
            messagebox.showinfo("Sucesso", "Mensagem salva com sucesso!")

        def restaurar_padrao():
            padrao = "Olá {nome}, passando para lembrar que seu acesso aos canais {empresa} vence em {vencimento}. Deseja renovar?"
            self.txt_msg_zap.delete("1.0", "end")
            self.txt_msg_zap.insert("1.0", padrao)
            atualizar_preview()

        btn_frame = tk.Frame(box_msg, bg="#f0f0f0")
        btn_frame.pack(anchor="w")
        ttk.Button(btn_frame, text="💾 SALVAR MENSAGEM", command=salvar_mensagem).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_frame, text="↩ Restaurar Padrão", command=restaurar_padrao).pack(side=tk.LEFT)

        # ── Mensagem para Clientes VENCIDOS ──
        box_venc = tk.LabelFrame(frame, text=" 📛 Mensagem para Clientes VENCIDOS ",
                                  bg="#f0f0f0", padx=20, pady=20, font=("Arial", 10, "bold"))
        box_venc.pack(fill="x", pady=(0, 20))

        tk.Label(box_venc, text="Mensagem enviada pelo botão '📛 AVISAR VENCIDOS' para clientes já vencidos.",
                 bg="#f0f0f0", font=("Arial", 9)).pack(anchor="w")
        tk.Label(box_venc, text="Variáveis disponíveis:  {nome}  |  {empresa}  |  {vencimento}",
                 bg="#f0f0f0", font=("Arial", 8, "italic"), fg="#1a3a6c").pack(anchor="w", pady=(2, 8))

        self.txt_msg_vencido = tk.Text(box_venc, height=4, width=80, font=("Arial", 10), wrap="word",
                                        relief="solid", bd=1)
        self.txt_msg_vencido.insert("1.0", self.get_mensagem_vencido())
        self.txt_msg_vencido.pack(fill="x", pady=(0, 8))

        lbl_preview_venc = tk.Label(box_venc, text="", bg="#f8d7da", fg="#721c24",
                                     font=("Arial", 8, "italic"), wraplength=700,
                                     justify="left", padx=8, pady=5, relief="solid", bd=1)
        lbl_preview_venc.pack(fill="x", pady=(0, 8))

        def atualizar_preview_vencido(*args):
            t = self.txt_msg_vencido.get("1.0", "end-1c")
            preview = (t.replace("{nome}", "João Silva")
                        .replace("{empresa}", self.get_nome_empresa())
                        .replace("{vencimento}", "01/04/2026"))
            lbl_preview_venc.config(text="Prévia: " + preview)

        self.txt_msg_vencido.bind("<KeyRelease>", atualizar_preview_vencido)
        atualizar_preview_vencido()

        def salvar_msg_vencido():
            msg = self.txt_msg_vencido.get("1.0", "end-1c").strip()
            if not msg:
                messagebox.showwarning("Aviso", "A mensagem não pode estar vazia!"); return
            self.salvar_mensagem_vencido(msg)
            messagebox.showinfo("Sucesso", "Mensagem para vencidos salva!")

        def restaurar_padrao_vencido():
            padrao = "Olá {nome}, seu acesso aos canais {empresa} venceu em {vencimento}. Renove agora para não ficar sem acesso!"
            self.txt_msg_vencido.delete("1.0", "end")
            self.txt_msg_vencido.insert("1.0", padrao)
            atualizar_preview_vencido()

        btn_venc_frame = tk.Frame(box_venc, bg="#f0f0f0")
        btn_venc_frame.pack(anchor="w")
        ttk.Button(btn_venc_frame, text="💾 SALVAR MENSAGEM", command=salvar_msg_vencido).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_venc_frame, text="↩ Restaurar Padrão", command=restaurar_padrao_vencido).pack(side=tk.LEFT)
        ttk.Button(btn_venc_frame, text="📛 TESTAR ENVIO (selecionado)",
                   command=self.disparar_avisos_vencidos).pack(side=tk.LEFT, padx=(16, 0))

        # ── Exclusão Automática ──
        box_exc = tk.LabelFrame(frame, text=" Exclusão Automática de Vencidos ", bg="#f0f0f0", padx=20, pady=20, font=("Arial", 10, "bold"))
        box_exc.pack(fill="x", pady=(0, 20))

        tk.Label(box_exc, text="Excluir automaticamente clientes vencidos após quantos dias?",
                 bg="#f0f0f0", font=("Arial", 9)).pack(anchor="w")
        tk.Label(box_exc, text='Deixe em branco ou 0 para desativar. O sistema verifica a cada 5 minutos.',
                 bg="#f0f0f0", font=("Arial", 8, "italic"), fg="#721c24").pack(anchor="w", pady=(2, 10))

        exc_frame = tk.Frame(box_exc, bg="#f0f0f0")
        exc_frame.pack(anchor="w")

        # Ler valor atual do banco
        with self.conectar() as conn:
            row_exc = conn.execute("SELECT valor FROM config WHERE chave='exclusao_auto_dias'").fetchone()
            val_exc_atual = row_exc[0] if row_exc else ""

        self.ent_exclusao_dias = ttk.Entry(exc_frame, width=10)
        self.ent_exclusao_dias.insert(0, val_exc_atual)
        self.ent_exclusao_dias.pack(side=tk.LEFT, padx=(0, 5))
        tk.Label(exc_frame, text="dias após vencimento", bg="#f0f0f0", font=("Arial", 9)).pack(side=tk.LEFT, padx=(0, 15))

        def salvar_exclusao():
            val = self.ent_exclusao_dias.get().strip()
            if val and not val.isdigit():
                messagebox.showwarning("Aviso", "Digite apenas números!"); return
            with self.conectar() as conn:
                conn.execute("INSERT OR REPLACE INTO config (chave, valor) VALUES ('exclusao_auto_dias', ?)", (val,))
            if val and int(val) > 0:
                messagebox.showinfo("Salvo", f"Clientes serão excluídos automaticamente {val} dias após o vencimento.")
            else:
                messagebox.showinfo("Salvo", "Exclusão automática desativada.")

        ttk.Button(exc_frame, text="💾 SALVAR", command=salvar_exclusao).pack(side=tk.LEFT)

        # ── Alterar Senha do Sistema ──
        box_pw = tk.LabelFrame(frame, text=" Alterar Senha de Login ", bg="#f0f0f0",
                               padx=20, pady=15, font=("Arial", 10, "bold"))
        box_pw.pack(fill="x", pady=(0, 20))

        pw_frame = tk.Frame(box_pw, bg="#f0f0f0")
        pw_frame.pack(anchor="w")
        tk.Label(pw_frame, text="Usuário:",    bg="#f0f0f0", width=14, anchor="w").grid(row=0, column=0, pady=3)
        ent_pw_user = ttk.Entry(pw_frame, width=22); ent_pw_user.grid(row=0, column=1, padx=5)
        tk.Label(pw_frame, text="Nova senha:", bg="#f0f0f0", width=14, anchor="w").grid(row=1, column=0, pady=3)
        ent_pw_new  = ttk.Entry(pw_frame, width=22, show="*"); ent_pw_new.grid(row=1, column=1, padx=5)
        tk.Label(pw_frame, text="Confirmar:",  bg="#f0f0f0", width=14, anchor="w").grid(row=2, column=0, pady=3)
        ent_pw_conf = ttk.Entry(pw_frame, width=22, show="*"); ent_pw_conf.grid(row=2, column=1, padx=5)

        def alterar_senha():
            u     = ent_pw_user.get().strip()
            new_p = ent_pw_new.get().strip()
            conf  = ent_pw_conf.get().strip()
            if not all([u, new_p, conf]):
                messagebox.showwarning("Aviso", "Preencha todos os campos!"); return
            if len(new_p) < 6:
                messagebox.showerror("Erro", "Nova senha deve ter ao menos 6 caracteres!"); return
            if new_p != conf:
                messagebox.showerror("Erro", "Nova senha e confirmação não coincidem!"); return
            import sqlite3 as _sq
            conn = _sq.connect(DB_FILE)
            row = conn.execute("SELECT id FROM usuarios_sistema WHERE usuario=?", (u,)).fetchone()
            if not row:
                conn.close(); messagebox.showerror("Erro", "Usuário não encontrado!"); return
            conn.execute("UPDATE usuarios_sistema SET senha_hash=? WHERE usuario=?", (hash_senha(new_p), u))
            conn.commit(); conn.close()
            messagebox.showinfo("Sucesso", f"Senha de '{u}' alterada com sucesso!")
            for e in (ent_pw_new, ent_pw_conf): e.delete(0, tk.END)

        ttk.Button(pw_frame, text="🔒 ALTERAR SENHA", command=alterar_senha).grid(row=3, column=0, columnspan=2, pady=10)


        # ── Gerenciar Usuários do Sistema ──
        box_usr = tk.LabelFrame(frame, text=" 👤 Gerenciar Usuários do Sistema ",
                                bg="#f0f0f0", padx=20, pady=15, font=("Arial", 10, "bold"))
        box_usr.pack(fill="x", pady=(0, 20))

        tk.Label(box_usr, text="Adicione, edite ou remova usuários. Defina o perfil de acesso de cada um.",
                 bg="#f0f0f0", font=("Arial", 9)).pack(anchor="w", pady=(0, 8))

        # Tabela com perfil visível
        frame_usr_tab = tk.Frame(box_usr, bg="#f0f0f0"); frame_usr_tab.pack(fill="x", pady=(0, 8))
        sb_usr = ttk.Scrollbar(frame_usr_tab, orient="vertical")
        self.tab_usuarios = ttk.Treeview(frame_usr_tab,
                                         columns=["ID", "USR", "EMAIL", "PERFIL"],
                                         show="headings", height=5,
                                         yscrollcommand=sb_usr.set)
        sb_usr.config(command=self.tab_usuarios.yview)
        self.tab_usuarios.heading("ID",     text="#");      self.tab_usuarios.column("ID",     width=35,  anchor="center")
        self.tab_usuarios.heading("USR",    text="Usuário");self.tab_usuarios.column("USR",    width=150)
        self.tab_usuarios.heading("EMAIL",  text="E-mail"); self.tab_usuarios.column("EMAIL",  width=200)
        self.tab_usuarios.heading("PERFIL", text="Perfil"); self.tab_usuarios.column("PERFIL", width=120, anchor="center")
        self.tab_usuarios.tag_configure("basico",       background="#e3f2fd")
        self.tab_usuarios.tag_configure("operador",     background="#e8f5e9")
        self.tab_usuarios.tag_configure("completo",     background="#f3e5f5")
        self.tab_usuarios.tag_configure("personalizado",background="#fff3cd")
        sb_usr.pack(side=tk.RIGHT, fill=tk.Y)
        self.tab_usuarios.pack(fill="x")

        # Formulário novo usuário
        frm_novo = tk.LabelFrame(box_usr, text=" Novo Usuário ", bg="#f0f0f0",
                                  padx=10, pady=8, font=("Arial", 9))
        frm_novo.pack(fill="x", pady=(10, 0))

        linha_f1 = tk.Frame(frm_novo, bg="#f0f0f0"); linha_f1.pack(fill="x", pady=(0, 4))
        tk.Label(linha_f1, text="Usuário:",  bg="#f0f0f0", font=("Arial", 9)).pack(side=tk.LEFT)
        ent_novo_usr = ttk.Entry(linha_f1, width=16); ent_novo_usr.pack(side=tk.LEFT, padx=(4, 12))
        tk.Label(linha_f1, text="Senha:",    bg="#f0f0f0", font=("Arial", 9)).pack(side=tk.LEFT)
        ent_novo_pw  = ttk.Entry(linha_f1, width=14, show="*"); ent_novo_pw.pack(side=tk.LEFT, padx=(4, 12))
        tk.Label(linha_f1, text="E-mail:",   bg="#f0f0f0", font=("Arial", 9)).pack(side=tk.LEFT)
        ent_novo_em  = ttk.Entry(linha_f1, width=20); ent_novo_em.pack(side=tk.LEFT, padx=(4, 12))

        linha_f2 = tk.Frame(frm_novo, bg="#f0f0f0"); linha_f2.pack(fill="x")
        tk.Label(linha_f2, text="Perfil:", bg="#f0f0f0", font=("Arial", 9)).pack(side=tk.LEFT)
        var_novo_perfil = tk.StringVar(value="completo")
        cmb_perfil = ttk.Combobox(linha_f2, textvariable=var_novo_perfil,
                                   values=["basico", "operador", "completo", "personalizado"],
                                   state="readonly", width=14)
        cmb_perfil.pack(side=tk.LEFT, padx=(4, 8))
        lbl_perfil_desc = tk.Label(linha_f2, text=PERFIS_PREDEFINIDOS["completo"]["descricao"],
                                    bg="#f0f0f0", fg="#555", font=("Arial", 8, "italic"))
        lbl_perfil_desc.pack(side=tk.LEFT, padx=(0, 8))
        btn_personalizar = ttk.Button(linha_f2, text="⚙ Personalizar Permissões")
        btn_personalizar.pack(side=tk.LEFT, padx=4)
        btn_personalizar.config(state="disabled")

        # Armazena permissões personalizadas temporárias
        _perms_custom = {"valor": []}

        def _atualizar_desc_perfil(*args):
            p = var_novo_perfil.get()
            desc = PERFIS_PREDEFINIDOS.get(p, {}).get("descricao", "")
            lbl_perfil_desc.config(text=desc)
            btn_personalizar.config(state="normal" if p == "personalizado" else "disabled")

        var_novo_perfil.trace_add("write", _atualizar_desc_perfil)

        def _janela_permissoes(titulo, perms_atuais, callback):
            """Abre janela para selecionar permissões manualmente."""
            jan_p = tk.Toplevel()
            jan_p.title(titulo)
            jan_p.geometry("420x460")
            jan_p.configure(bg="#f0f0f0")
            jan_p.resizable(False, False)
            jan_p.grab_set()
            sw = jan_p.winfo_screenwidth(); sh = jan_p.winfo_screenheight()
            jan_p.geometry(f"420x460+{(sw-420)//2}+{(sh-460)//2}")

            tk.Label(jan_p, text="⚙ PERMISSÕES PERSONALIZADAS",
                     font=("Arial", 11, "bold"), bg="#f0f0f0", fg="#1a3a6c").pack(pady=(14, 4))
            tk.Label(jan_p, text="Marque as permissões que este usuário terá:",
                     bg="#f0f0f0", font=("Arial", 9)).pack(pady=(0, 10))

            frame_chk = tk.Frame(jan_p, bg="#f0f0f0", padx=20); frame_chk.pack(fill="x")
            vars_perm = {}
            for i, (chave, label) in enumerate(PERMISSOES_DISPONIVEIS.items()):
                var = tk.BooleanVar(value=(chave in perms_atuais))
                tk.Checkbutton(frame_chk, text=label, variable=var,
                               bg="#f0f0f0", font=("Arial", 9),
                               anchor="w").grid(row=i//2, column=i%2, sticky="w", padx=8, pady=2)
                vars_perm[chave] = var

            frm_acao = tk.Frame(jan_p, bg="#f0f0f0"); frm_acao.pack(pady=16)

            def marcar_todos():
                for v in vars_perm.values(): v.set(True)
            def desmarcar_todos():
                for v in vars_perm.values(): v.set(False)

            ttk.Button(frm_acao, text="✅ Marcar Todos",   command=marcar_todos).pack(side=tk.LEFT, padx=4)
            ttk.Button(frm_acao, text="✖ Desmarcar Todos", command=desmarcar_todos).pack(side=tk.LEFT, padx=4)

            def confirmar():
                selecionadas = [k for k, v in vars_perm.items() if v.get()]
                callback(selecionadas)
                jan_p.destroy()

            tk.Button(jan_p, text="💾 CONFIRMAR", bg="#1a3a6c", fg="white",
                      font=("Arial", 10, "bold"), relief="flat", padx=16, pady=7,
                      cursor="hand2", command=confirmar).pack(pady=(0, 10))

        def abrir_personalizar():
            _janela_permissoes(
                "Personalizar Permissões — Novo Usuário",
                _perms_custom["valor"],
                lambda p: _perms_custom.update({"valor": p})
            )

        btn_personalizar.config(command=abrir_personalizar)

        def carregar_usuarios():
            for i in self.tab_usuarios.get_children(): self.tab_usuarios.delete(i)
            with self.conectar() as conn:
                try:
                    rows = conn.execute(
                        "SELECT id, usuario, COALESCE(email,''), COALESCE(perfil,'completo') "
                        "FROM usuarios_sistema ORDER BY usuario"
                    ).fetchall()
                except:
                    rows = conn.execute(
                        "SELECT id, usuario, COALESCE(email,''), 'completo' "
                        "FROM usuarios_sistema ORDER BY usuario"
                    ).fetchall()
            for uid, usr, em, perfil in rows:
                label_perfil = PERFIS_PREDEFINIDOS.get(perfil, {}).get("label", perfil.capitalize())
                self.tab_usuarios.insert("", "end",
                                          values=(uid, usr, em, label_perfil),
                                          tags=(perfil,))

        def adicionar_usuario():
            u  = ent_novo_usr.get().strip()
            p  = ent_novo_pw.get().strip()
            em = ent_novo_em.get().strip()
            perf = var_novo_perfil.get()
            if not u or not p:
                messagebox.showwarning("Aviso", "Preencha ao menos usuário e senha!"); return
            if len(p) < 6:
                messagebox.showwarning("Aviso", "Senha mínimo 6 caracteres!"); return
            if em and "@" not in em:
                messagebox.showwarning("Aviso", "E-mail inválido!"); return
            perms_json = json.dumps(_perms_custom["valor"]) if perf == "personalizado" else ""
            try:
                with self.conectar() as conn:
                    conn.execute(
                        "INSERT INTO usuarios_sistema (usuario, senha_hash, email, perfil, permissoes) "
                        "VALUES (?,?,?,?,?)",
                        (u, hash_senha(p), em, perf, perms_json))
                messagebox.showinfo("Sucesso", f"Usuário '{u}' criado com perfil '{perf}'!")
                ent_novo_usr.delete(0, tk.END); ent_novo_pw.delete(0, tk.END)
                ent_novo_em.delete(0, tk.END); var_novo_perfil.set("completo")
                _perms_custom["valor"] = []
                carregar_usuarios()
            except Exception as ex:
                messagebox.showerror("Erro", f"Usuário já existe ou erro: {ex}")

        def editar_usuario():
            sel = self.tab_usuarios.selection()
            if not sel:
                messagebox.showwarning("Aviso", "Selecione um usuário para editar!"); return
            vals = self.tab_usuarios.item(sel[0])['values']
            uid = vals[0]; usr_atual = vals[1]; email_atual = vals[2]

            # Busca perfil e permissões reais do banco
            with self.conectar() as conn:
                try:
                    row_db = conn.execute(
                        "SELECT COALESCE(perfil,'completo'), COALESCE(permissoes,'') "
                        "FROM usuarios_sistema WHERE id=?", (uid,)
                    ).fetchone()
                except:
                    row_db = ("completo", "")
            perfil_atual   = row_db[0] if row_db else "completo"
            perms_atual_json = row_db[1] if row_db else ""
            try:
                perms_atual = json.loads(perms_atual_json) if perms_atual_json else []
            except:
                perms_atual = []

            _perms_edit = {"valor": perms_atual}

            jan_edit = tk.Toplevel()
            jan_edit.title(f"Editar — {usr_atual}")
            jan_edit.geometry("420x360")
            jan_edit.configure(bg="#f0f0f0")
            jan_edit.resizable(False, False)
            jan_edit.grab_set()
            sw = jan_edit.winfo_screenwidth(); sh = jan_edit.winfo_screenheight()
            jan_edit.geometry(f"420x360+{(sw-420)//2}+{(sh-360)//2}")

            tk.Label(jan_edit, text=f"✎ Editando: {usr_atual}",
                     font=("Arial", 11, "bold"), bg="#f0f0f0", fg="#1a3a6c").pack(pady=(14, 8))

            frm_e = tk.Frame(jan_edit, bg="#f0f0f0", padx=24); frm_e.pack(fill="x")

            tk.Label(frm_e, text="Novo usuário:",  bg="#f0f0f0", width=18, anchor="w").grid(row=0, column=0, pady=5)
            ent_e_usr = ttk.Entry(frm_e, width=26); ent_e_usr.grid(row=0, column=1, padx=5)
            ent_e_usr.insert(0, usr_atual)

            tk.Label(frm_e, text="Nova senha:",    bg="#f0f0f0", width=18, anchor="w").grid(row=1, column=0, pady=5)
            ent_e_pw = ttk.Entry(frm_e, width=26, show="*"); ent_e_pw.grid(row=1, column=1, padx=5)
            tk.Label(frm_e, text="(em branco = não altera)", bg="#f0f0f0",
                     font=("Arial", 7, "italic"), fg="#888").grid(row=2, column=1, sticky="w")

            tk.Label(frm_e, text="E-mail:",        bg="#f0f0f0", width=18, anchor="w").grid(row=3, column=0, pady=5)
            ent_e_em = ttk.Entry(frm_e, width=26); ent_e_em.grid(row=3, column=1, padx=5)
            ent_e_em.insert(0, email_atual or "")

            tk.Label(frm_e, text="Perfil:",        bg="#f0f0f0", width=18, anchor="w").grid(row=4, column=0, pady=5)
            frm_perf = tk.Frame(frm_e, bg="#f0f0f0"); frm_perf.grid(row=4, column=1, sticky="w")
            var_e_perfil = tk.StringVar(value=perfil_atual)
            cmb_e_perf = ttk.Combobox(frm_perf, textvariable=var_e_perfil,
                                       values=["basico", "operador", "completo", "personalizado"],
                                       state="readonly", width=14)
            cmb_e_perf.pack(side=tk.LEFT)
            btn_e_custom = ttk.Button(frm_perf, text="⚙ Permissões",
                                       state="normal" if perfil_atual == "personalizado" else "disabled")
            btn_e_custom.pack(side=tk.LEFT, padx=(6, 0))

            def _toggle_e_custom(*a):
                btn_e_custom.config(state="normal" if var_e_perfil.get() == "personalizado" else "disabled")
            var_e_perfil.trace_add("write", _toggle_e_custom)

            def _abrir_perms_edit():
                _janela_permissoes(
                    f"Permissões — {usr_atual}",
                    _perms_edit["valor"],
                    lambda p: _perms_edit.update({"valor": p})
                )
            btn_e_custom.config(command=_abrir_perms_edit)

            lbl_err = tk.Label(jan_edit, text="", bg="#f0f0f0", fg="#721c24", font=("Arial", 9))
            lbl_err.pack(pady=(6, 0))

            def salvar_edicao():
                novo_usr = ent_e_usr.get().strip()
                nova_pw  = ent_e_pw.get().strip()
                novo_em  = ent_e_em.get().strip()
                novo_perf = var_e_perfil.get()
                if not novo_usr:
                    lbl_err.config(text="Usuário não pode ficar vazio!"); return
                if nova_pw and len(nova_pw) < 6:
                    lbl_err.config(text="Senha mínimo 6 caracteres!"); return
                if novo_em and "@" not in novo_em:
                    lbl_err.config(text="E-mail inválido!"); return
                perms_json = json.dumps(_perms_edit["valor"]) if novo_perf == "personalizado" else ""
                with self.conectar() as conn:
                    if nova_pw:
                        conn.execute(
                            "UPDATE usuarios_sistema SET usuario=?, senha_hash=?, email=?, perfil=?, permissoes=? WHERE id=?",
                            (novo_usr, hash_senha(nova_pw), novo_em, novo_perf, perms_json, uid))
                    else:
                        conn.execute(
                            "UPDATE usuarios_sistema SET usuario=?, email=?, perfil=?, permissoes=? WHERE id=?",
                            (novo_usr, novo_em, novo_perf, perms_json, uid))
                messagebox.showinfo("Salvo", "Usuário atualizado!")
                jan_edit.destroy(); carregar_usuarios()

            tk.Button(jan_edit, text="💾 SALVAR ALTERAÇÕES", bg="#1a3a6c", fg="white",
                      font=("Arial", 10, "bold"), relief="flat", padx=14, pady=7,
                      cursor="hand2", command=salvar_edicao).pack(pady=(10, 0))

        def remover_usuario():
            sel = self.tab_usuarios.selection()
            if not sel:
                messagebox.showwarning("Aviso", "Selecione um usuário!"); return
            uid, usr = self.tab_usuarios.item(sel[0])['values'][:2]
            with self.conectar() as conn:
                total = conn.execute("SELECT COUNT(*) FROM usuarios_sistema").fetchone()[0]
            if total <= 1:
                messagebox.showerror("Erro", "Não é possível remover o único usuário!"); return
            if messagebox.askyesno("Remover", f"Remover usuário '{usr}'?"):
                with self.conectar() as conn:
                    conn.execute("DELETE FROM usuarios_sistema WHERE id=?", (uid,))
                carregar_usuarios()

        btn_usr = tk.Frame(box_usr, bg="#f0f0f0"); btn_usr.pack(anchor="w", pady=(10, 0))
        ttk.Button(btn_usr, text="➕ ADICIONAR",          command=adicionar_usuario).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_usr, text="✏ EDITAR SELECIONADO",  command=editar_usuario).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_usr, text="🗑 REMOVER SELECIONADO", command=remover_usuario).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_usr, text="🔄 Atualizar",           command=carregar_usuarios).pack(side=tk.LEFT, padx=5)

        # Legenda de perfis
        frm_leg = tk.Frame(box_usr, bg="#f0f0f0"); frm_leg.pack(anchor="w", pady=(8, 0))
        tk.Label(frm_leg, text="Perfis: ", bg="#f0f0f0", font=("Arial", 8, "bold")).pack(side=tk.LEFT)
        for pk, pv in PERFIS_PREDEFINIDOS.items():
            cores = {"basico":"#e3f2fd","operador":"#e8f5e9","completo":"#f3e5f5","personalizado":"#fff3cd"}
            tk.Label(frm_leg, text=f" {pv['label']} ", bg=cores.get(pk,"#f0f0f0"),
                     font=("Arial", 8), relief="solid", bd=1,
                     padx=4).pack(side=tk.LEFT, padx=3)
            tk.Label(frm_leg, text=f"— {pv['descricao']}  ",
                     bg="#f0f0f0", font=("Arial", 8), fg="#555").pack(side=tk.LEFT)

        carregar_usuarios()

        # ── WhatsApp Business API ──────────────────────────────────────────────
        box_wpp = tk.LabelFrame(frame, text=" 📱 WhatsApp Business API (Meta) ",
                                bg="#f0f0f0", padx=20, pady=15, font=("Arial", 10, "bold"))
        box_wpp.pack(fill="x", pady=(0, 20))

        tk.Label(box_wpp,
                 text="Configure seu Token e Phone Number ID obtidos no Meta for Developers.",
                 bg="#f0f0f0", font=("Arial", 9)).pack(anchor="w")
        tk.Label(box_wpp,
                 text="Acesse: developers.facebook.com → Seu App → WhatsApp → Configuração da API",
                 bg="#f0f0f0", font=("Arial", 8, "italic"), fg="#1a3a6c").pack(anchor="w", pady=(0,10))

        wpp_frame = tk.Frame(box_wpp, bg="#f0f0f0"); wpp_frame.pack(anchor="w", fill="x")

        def wpp_row(parent, row, label, chave, show="", width=45):
            tk.Label(parent, text=label, bg="#f0f0f0", font=("Arial", 9),
                     width=20, anchor="e").grid(row=row, column=0, pady=4, padx=(0,6), sticky="e")
            var = tk.StringVar(value=self._get_config(chave))
            ent = ttk.Entry(parent, textvariable=var, width=width, show=show)
            ent.grid(row=row, column=1, pady=4, sticky="w")
            return var

        var_token      = wpp_row(wpp_frame, 0, "Access Token:",        'wpp_token',       show="*")
        var_phone_id   = wpp_row(wpp_frame, 1, "Phone Number ID:",     'wpp_phone_id')
        var_verify_tok = wpp_row(wpp_frame, 2, "Verify Token (hook):", 'wpp_verify_token', width=25)
        var_hook_port  = wpp_row(wpp_frame, 3, "Porta do Webhook:",    'wpp_webhook_port', width=8)

        frame_auto = tk.Frame(box_wpp, bg="#f0f0f0"); frame_auto.pack(anchor="w", pady=(8,0))
        var_auto = tk.BooleanVar(value=self._get_config('wpp_auto_avisos') == '1')
        tk.Checkbutton(frame_auto, text="Enviar avisos automáticos de vencimento a cada 5 min",
                       variable=var_auto, bg="#f0f0f0", font=("Arial", 9)).pack(side=tk.LEFT)
        tk.Label(frame_auto, text=" — dias de antecedência:", bg="#f0f0f0", font=("Arial", 9)).pack(side=tk.LEFT)
        var_dias_av = tk.StringVar(value=self._get_config('wpp_dias_aviso') or '3')
        ttk.Entry(frame_auto, textvariable=var_dias_av, width=4).pack(side=tk.LEFT, padx=4)

        self._lbl_wpp_status = tk.Label(box_wpp, text="⚪ Webhook não iniciado",
                                         bg="#f0f0f0", font=("Arial", 9, "italic"), fg="#555")
        self._lbl_wpp_status.pack(anchor="w", pady=(6,0))

        def salvar_wpp_config():
            self._set_config('wpp_token',        var_token.get().strip())
            self._set_config('wpp_phone_id',     var_phone_id.get().strip())
            self._set_config('wpp_verify_token', var_verify_tok.get().strip())
            self._set_config('wpp_webhook_port', var_hook_port.get().strip())
            self._set_config('wpp_auto_avisos',  '1' if var_auto.get() else '0')
            self._set_config('wpp_dias_aviso',   var_dias_av.get().strip() or '3')
            messagebox.showinfo("Salvo", "Configurações da API salvas com sucesso!")

        def testar_conexao():
            if not REQUESTS_OK:
                messagebox.showerror("Erro", "Instale o pacote requests:\npip install requests"); return
            token    = var_token.get().strip()
            phone_id = var_phone_id.get().strip()
            if not token or not phone_id:
                messagebox.showwarning("Aviso", "Preencha Token e Phone Number ID!"); return
            try:
                url  = f"https://graph.facebook.com/v19.0/{phone_id}"
                r    = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=8)
                data = r.json()
                if "id" in data:
                    messagebox.showinfo("✅ Conexão OK",
                        f"Conectado!\nNúmero: {data.get('display_phone_number','?')}\n"
                        f"Nome verificado: {data.get('verified_name','?')}")
                else:
                    err = data.get("error", {}).get("message", str(data))
                    messagebox.showerror("❌ Erro", f"Resposta da Meta:\n{err}")
            except Exception as e:
                messagebox.showerror("Erro de conexão", str(e))

        def iniciar_webhook_btn():
            salvar_wpp_config()
            port = self.iniciar_webhook()
            self._lbl_wpp_status.config(
                text=f"🟢 Webhook ativo na porta {port}  —  "
                     f"Para testes locais use ngrok: ngrok http {port}",
                fg="#1e5631")

        def enviar_avisos_btn():
            salvar_wpp_config()
            threading.Thread(target=lambda: self.disparar_avisos_vencimento(silencioso=False),
                             daemon=True).start()

        btn_wpp = tk.Frame(box_wpp, bg="#f0f0f0"); btn_wpp.pack(anchor="w", pady=(10,0))
        tk.Button(btn_wpp, text="💾 SALVAR CONFIG", bg="#1a3a6c", fg="white",
                  font=("Arial", 9, "bold"), relief="flat", padx=10, pady=5,
                  cursor="hand2", command=salvar_wpp_config).pack(side=tk.LEFT, padx=(0,6))
        tk.Button(btn_wpp, text="🔌 TESTAR CONEXÃO", bg="#1e5631", fg="white",
                  font=("Arial", 9, "bold"), relief="flat", padx=10, pady=5,
                  cursor="hand2", command=testar_conexao).pack(side=tk.LEFT, padx=6)
        tk.Button(btn_wpp, text="📡 INICIAR WEBHOOK", bg="#856404", fg="white",
                  font=("Arial", 9, "bold"), relief="flat", padx=10, pady=5,
                  cursor="hand2", command=iniciar_webhook_btn).pack(side=tk.LEFT, padx=6)
        tk.Button(btn_wpp, text="📢 ENVIAR AVISOS AGORA", bg="#721c24", fg="white",
                  font=("Arial", 9, "bold"), relief="flat", padx=10, pady=5,
                  cursor="hand2", command=enviar_avisos_btn).pack(side=tk.LEFT, padx=6)
        tk.Button(btn_wpp, text="📛 AVISAR VENCIDOS", bg="#8B0000", fg="white",
                  font=("Arial", 9, "bold"), relief="flat", padx=10, pady=5,
                  cursor="hand2",
                  command=self.disparar_avisos_vencidos).pack(side=tk.LEFT, padx=6)

        tk.Label(box_wpp,
                 text="⚠ O Webhook precisa de uma URL pública. Use ngrok (ngrok.com) para testes locais.",
                 bg="#f0f0f0", font=("Arial", 8, "italic"), fg="#856404").pack(anchor="w", pady=(8,0))

        # ── Configuração de Rede Local (Multimáquina) ──
        box_rede = tk.LabelFrame(frame, text=" 🖥 Uso em Rede Local (várias máquinas) ",
                                 bg="#f0f0f0", padx=20, pady=15, font=("Arial", 10, "bold"))
        box_rede.pack(fill="x", padx=20, pady=(10, 6))

        tk.Label(box_rede,
                 text="Permite que outras máquinas na mesma rede acessem o mesmo banco de dados.",
                 bg="#f0f0f0", font=("Arial", 9)).pack(anchor="w", pady=(0, 4))

        # Detectar IP local
        import socket as _sock
        try:
            _ip = _sock.gethostbyname(_sock.gethostname())
        except: _ip = "desconhecido"

        tk.Label(box_rede,
                 text=f"IP desta máquina na rede: {_ip}",
                 bg="#f0f0f0", font=("Arial", 9, "bold"), fg="#1a3a6c").pack(anchor="w", pady=(0, 10))

        frm_rede = tk.Frame(box_rede, bg="#f0f0f0"); frm_rede.pack(fill="x")

        tk.Label(frm_rede, text="Caminho do banco:", bg="#f0f0f0",
                 font=("Arial", 9, "bold")).grid(row=0, column=0, sticky="w", pady=4)

        var_db_path = tk.StringVar(value=DB_FILE)
        ent_db = ttk.Entry(frm_rede, textvariable=var_db_path, width=46, font=("Arial", 9))
        ent_db.grid(row=0, column=1, padx=8)

        def escolher_caminho_db():
            from tkinter import filedialog
            p = filedialog.asksaveasfilename(
                title="Escolha onde salvar/apontar o banco de dados",
                defaultextension=".db",
                filetypes=[("Banco SQLite", "*.db"), ("Todos", "*.*")],
                initialfile="tech_prime_plus.db")
            if p: var_db_path.set(p)

        tk.Button(frm_rede, text="📂 Navegar", bg="#1a3a6c", fg="white",
                  font=("Arial", 9), relief="flat", padx=8, pady=4,
                  cursor="hand2", command=escolher_caminho_db).grid(row=0, column=2, padx=(4,0))

        def salvar_config_rede():
            caminho = var_db_path.get().strip()
            if not caminho:
                messagebox.showwarning("Aviso", "Informe o caminho do banco!"); return
            pasta = os.path.dirname(caminho)
            if pasta and not os.path.exists(pasta):
                messagebox.showerror("Erro", f"Pasta não encontrada:\n{pasta}"); return
            with open(_DB_CONFIG_FILE, "w", encoding="utf-8") as f_cfg:
                f_cfg.write(caminho)
            messagebox.showinfo("Salvo", f"Configuração salva!\n\nO sistema usará o banco:\n{caminho}\n\nReinicie o sistema para aplicar.")

        def restaurar_local():
            if os.path.exists(_DB_CONFIG_FILE): os.remove(_DB_CONFIG_FILE)
            var_db_path.set("tech_prime_plus.db")
            messagebox.showinfo("Restaurado", "Voltou para o banco local.\nReinicie o sistema.")

        frm_rede_btns = tk.Frame(box_rede, bg="#f0f0f0"); frm_rede_btns.pack(anchor="w", pady=(10, 0))
        tk.Button(frm_rede_btns, text="💾 SALVAR CONFIGURAÇÃO", bg="#1a3a6c", fg="white",
                  font=("Arial", 9, "bold"), relief="flat", padx=10, pady=5,
                  cursor="hand2", command=salvar_config_rede).pack(side=tk.LEFT, padx=(0,8))
        tk.Button(frm_rede_btns, text="🏠 USAR BANCO LOCAL", bg="#856404", fg="white",
                  font=("Arial", 9, "bold"), relief="flat", padx=10, pady=5,
                  cursor="hand2", command=restaurar_local).pack(side=tk.LEFT)

        tk.Label(box_rede,
                 text="💡 Na máquina SERVIDOR: mantenha o banco local. "
                      "Nas máquinas CLIENTES: aponte para \\IP-SERVIDOR\\pasta\\tech_prime_plus.db",
                 bg="#f0f0f0", font=("Arial", 8, "italic"), fg="#555",
                 wraplength=560, justify="left").pack(anchor="w", pady=(10, 0))

        # ── Atualizar E-mail da Conta ──
        box_email_usr = tk.LabelFrame(frame, text=" ✉ E-mail de Recuperação da Conta ",
                                      bg="#f0f0f0", padx=12, pady=10,
                                      font=("Arial", 9, "bold"), fg="#1a3a6c")
        box_email_usr.pack(fill="x", padx=20, pady=(10, 10))

        tk.Label(box_email_usr,
                 text="Este e-mail será usado para receber a senha temporária caso esqueça o acesso.",
                 bg="#f0f0f0", font=("Arial", 8, "italic"), fg="#555").grid(
                 row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))

        tk.Label(box_email_usr, text="E-mail:", bg="#f0f0f0",
                 font=("Arial", 10, "bold")).grid(row=1, column=0, sticky="w", pady=4)
        var_email_usr = tk.StringVar()
        ttk.Entry(box_email_usr, textvariable=var_email_usr, width=36,
                  font=("Arial", 10)).grid(row=1, column=1, padx=8)
        try:
            with self.conectar() as _c:
                row_em = _c.execute(
                    "SELECT email FROM usuarios_sistema ORDER BY id LIMIT 1").fetchone()
                if row_em and row_em[0]: var_email_usr.set(row_em[0])
        except: pass

        def salvar_email_usuario():
            novo = var_email_usr.get().strip()
            if "@" not in novo or "." not in novo:
                messagebox.showwarning("Inválido", "Informe um e-mail válido!"); return
            import sqlite3 as _sq
            conn = _sq.connect(DB_FILE)
            conn.execute(
                "UPDATE usuarios_sistema SET email=? WHERE id=(SELECT MIN(id) FROM usuarios_sistema)",
                (novo,))
            conn.commit(); conn.close()
            messagebox.showinfo("Salvo", f"E-mail de recuperação atualizado:\n{novo}")

        tk.Button(box_email_usr, text="💾 SALVAR", bg="#1a3a6c", fg="white",
                  font=("Arial", 9, "bold"), relief="flat", padx=10, pady=5,
                  cursor="hand2", command=salvar_email_usuario).grid(row=1, column=2, padx=8)

        # ── Alterar e-mail do usuário logado ──
        box_email_usr = tk.LabelFrame(frame, text=" ✉ Atualizar E-mail da Conta ",
                                      bg="#f0f0f0", padx=12, pady=10, font=("Arial", 9, "bold"), fg="#1a3a6c")
        box_email_usr.pack(fill="x", padx=20, pady=(0, 10))

        tk.Label(box_email_usr, text="Novo e-mail:", bg="#f0f0f0", font=("Arial", 9, "bold")).grid(row=0, column=0, sticky="w", pady=4)
        var_email_usr = tk.StringVar()
        ttk.Entry(box_email_usr, textvariable=var_email_usr, width=36, font=("Arial", 10)).grid(row=0, column=1, padx=8)
        try:
            with self.conectar() as _c:
                row_em = _c.execute("SELECT email FROM usuarios_sistema ORDER BY id LIMIT 1").fetchone()
                if row_em and row_em[0]: var_email_usr.set(row_em[0])
        except: pass

        def salvar_email_usuario():
            novo = var_email_usr.get().strip()
            if "@" not in novo:
                messagebox.showwarning("Inválido", "Informe um e-mail válido!"); return
            import sqlite3 as _sq
            conn = _sq.connect(DB_FILE)
            conn.execute("UPDATE usuarios_sistema SET email=? WHERE id=(SELECT MIN(id) FROM usuarios_sistema)", (novo,))
            conn.commit(); conn.close()
            messagebox.showinfo("Salvo", f"E-mail atualizado para:\n{novo}")

        tk.Button(box_email_usr, text="💾 SALVAR E-MAIL", bg="#1a3a6c", fg="white",
                  font=("Arial", 9, "bold"), relief="flat", padx=10, pady=5,
                  cursor="hand2", command=salvar_email_usuario).grid(row=0, column=2, padx=8)

        # ── Atualização Automática ────────────────────────────────────────────
        box_upd = tk.LabelFrame(frame, text=" 🔄 Atualização Automática ",
                                bg="#f0f0f0", padx=20, pady=15, font=("Arial", 10, "bold"))
        box_upd.pack(fill="x", padx=20, pady=(10, 20))

        tk.Label(box_upd,
                 text=f"Versão atual: v{VERSAO_ATUAL}",
                 bg="#f0f0f0", font=("Arial", 11, "bold"), fg="#1a3a6c").pack(anchor="w")
        tk.Label(box_upd,
                 text=f"Repositório: github.com/{GITHUB_REPO}",
                 bg="#f0f0f0", font=("Arial", 8, "italic"), fg="#555").pack(anchor="w", pady=(0, 10))

        self._lbl_update_status = tk.Label(box_upd, text="",
                                           bg="#f0f0f0", font=("Arial", 9), fg="#333")
        self._lbl_update_status.pack(anchor="w", pady=(0, 8))

        self._update_info = {"data": None}

        cfg_upd = _carregar_config_update()
        var_auto_check = tk.BooleanVar(value=cfg_upd.get("auto_check", True))

        tk.Checkbutton(box_upd, text="Verificar atualizações automaticamente ao iniciar",
                       variable=var_auto_check, bg="#f0f0f0", font=("Arial", 9),
                       command=lambda: _salvar_config_update({"auto_check": var_auto_check.get()})
                       ).pack(anchor="w", pady=(0, 8))

        def _on_check_result(tem_update, info):
            def _update_ui():
                if tem_update:
                    self._update_info["data"] = info
                    self._lbl_update_status.config(
                        text=f"Nova versão disponível: v{info['versao_nova']}",
                        fg="#1e5631", font=("Arial", 10, "bold"))
                    btn_atualizar.config(state="normal")
                else:
                    erro = info.get("erro", "")
                    if erro:
                        self._lbl_update_status.config(
                            text=f"Erro ao verificar: {erro}", fg="#721c24")
                    else:
                        self._lbl_update_status.config(
                            text=f"Você está na versão mais recente (v{VERSAO_ATUAL})",
                            fg="#1e5631")
                    btn_atualizar.config(state="disabled")
            self.root.after(0, _update_ui)

        def verificar_agora():
            self._lbl_update_status.config(text="Verificando...", fg="#856404")
            btn_atualizar.config(state="disabled")
            verificar_atualizacao_github(callback_resultado=_on_check_result)

        def aplicar_update():
            info = self._update_info.get("data")
            if not info:
                messagebox.showwarning("Aviso", "Nenhuma atualização encontrada. Verifique primeiro.")
                return
            if messagebox.askyesno("Confirmar Atualização",
                    f"Atualizar de v{info['versao_atual']} para v{info['versao_nova']}?\n\n"
                    f"Um backup da versão atual será criado automaticamente."):
                self._executar_atualizacao(info)

        btn_frame_upd = tk.Frame(box_upd, bg="#f0f0f0")
        btn_frame_upd.pack(anchor="w", pady=(0, 4))

        tk.Button(btn_frame_upd, text="🔍 VERIFICAR ATUALIZAÇÕES", bg="#1a3a6c", fg="white",
                  font=("Arial", 9, "bold"), relief="flat", padx=12, pady=6,
                  cursor="hand2", command=verificar_agora).pack(side=tk.LEFT, padx=(0, 8))

        btn_atualizar = tk.Button(btn_frame_upd, text="⬇ ATUALIZAR AGORA", bg="#1e5631", fg="white",
                                   font=("Arial", 9, "bold"), relief="flat", padx=12, pady=6,
                                   cursor="hand2", command=aplicar_update, state="disabled")
        btn_atualizar.pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(box_upd,
                 text="💡 As atualizações são baixadas diretamente do GitHub. "
                      "Um backup da versão anterior é salvo automaticamente.",
                 bg="#f0f0f0", fg="#555", font=("Arial", 8, "italic"),
                 wraplength=560, justify="left").pack(anchor="w", pady=(6, 0))


class JanelaLogin:
    def __init__(self, root_principal, callback_ok):
        self.window = tk.Toplevel(root_principal)
        self.root_ref = root_principal
        self.window.title("Login - TECH PRIME PLUS")
        self.window.configure(bg="#1a3a6c")
        self.window.resizable(False, False)
        self.window.grab_set()
        self.callback = callback_ok
        eh_primeiro = primeiro_acesso()
        altura = 560 if eh_primeiro else 430
        self.window.update_idletasks()
        sw = self.window.winfo_screenwidth(); sh = self.window.winfo_screenheight()
        self.window.geometry(f"440x{altura}+{(sw-440)//2}+{(sh-altura)//2}")
        try: self.window.iconbitmap("logo.ico")
        except: pass

        tk.Label(self.window, text="TECH PRIME PLUS", font=("Arial", 18, "bold"),
                 bg="#1a3a6c", fg="white").pack(pady=(25, 4))
        tk.Label(self.window, text="Acesso ao Sistema", font=("Arial", 10),
                 bg="#1a3a6c", fg="#aad4f5").pack(pady=(0, 15))

        frame = tk.Frame(self.window, bg="#f0f0f0", padx=35, pady=20)
        frame.pack(fill="x", padx=30)

        if eh_primeiro:
            tk.Label(frame,
                     text="Primeiro acesso — crie seu usuário administrador:",
                     bg="#fffbea", fg="#856404", font=("Arial", 8, "bold"),
                     relief="ridge", padx=8, pady=4).pack(fill="x", pady=(0, 10))

        tk.Label(frame, text="Usuário:", bg="#f0f0f0", font=("Arial", 10, "bold")).pack(anchor="w")
        self.ent_user = ttk.Entry(frame, width=32, font=("Arial", 11))
        self.ent_user.pack(fill="x", pady=(2, 8)); self.ent_user.focus()
        self.ent_user.bind("<Return>", lambda e: self.ent_pass.focus())

        tk.Label(frame, text="Senha:", bg="#f0f0f0", font=("Arial", 10, "bold")).pack(anchor="w")
        self.ent_pass = ttk.Entry(frame, width=32, show="*", font=("Arial", 11))
        self.ent_pass.pack(fill="x", pady=(2, 8))

        self.ent_email = None
        if eh_primeiro:
            self.ent_pass.bind("<Return>", lambda e: self.ent_email.focus())
            tk.Label(frame, text="E-mail (obrigatório — para recuperação de senha):",
                     bg="#f0f0f0", font=("Arial", 10, "bold")).pack(anchor="w")
            self.ent_email = ttk.Entry(frame, width=32, font=("Arial", 11))
            self.ent_email.pack(fill="x", pady=(2, 8))
            self.ent_email.bind("<Return>", lambda e: self.tentar_login())
        else:
            self.ent_pass.bind("<Return>", lambda e: self.tentar_login())

        self.lbl_erro = tk.Label(frame, text="", bg="#f0f0f0", fg="#721c24",
                                  font=("Arial", 9), wraplength=340)
        self.lbl_erro.pack(pady=(0, 4))

        tk.Button(frame, text="ENTRAR", bg="#1a3a6c", fg="white",
                  font=("Arial", 11, "bold"), relief="flat", cursor="hand2",
                  padx=10, pady=8, command=self.tentar_login).pack(fill="x", pady=(0, 6))

        if not eh_primeiro:
            tk.Button(frame, text="🔑 Esqueci minha senha", bg="#f0f0f0", fg="#1a3a6c",
                      font=("Arial", 8), relief="flat", cursor="hand2",
                      command=self.janela_recuperar_senha).pack()

    # ─────────────────────────────────────────────
    def tentar_login(self):
        u = self.ent_user.get().strip()
        p = self.ent_pass.get().strip()
        if not u or not p:
            self.lbl_erro.config(text="Preencha usuário e senha!"); return

        # Primeiro acesso — cadastro obrigatório com e-mail
        if primeiro_acesso():
            email = self.ent_email.get().strip() if self.ent_email else ""
            if not email or "@" not in email:
                self.lbl_erro.config(text="E-mail obrigatório e deve ser válido!"); return
            if len(p) < 6:
                self.lbl_erro.config(text="Senha muito curta (mínimo 6 caracteres)!"); return
            import sqlite3 as _sq
            conn = _sq.connect(DB_FILE)
            conn.execute("INSERT INTO usuarios_sistema (usuario, senha_hash, email) VALUES (?,?,?)",
                         (u, hash_senha(p), email))
            conn.commit(); conn.close()
            messagebox.showinfo("Cadastro criado",
                f"Usuário '{u}' criado!\n\nE-mail de recuperação: {email}\n\nFaça login agora.")
            self.ent_pass.delete(0, tk.END)
            if self.ent_email: self.ent_email.delete(0, tk.END)
            # Reabrir como tela de login normal
            cb = self.callback
            root_ref = self.root_ref
            self.window.destroy()
            JanelaLogin(root_ref, cb)
            return

        if verificar_login(u, p):
            # Bloqueia acesso visual do master para não confundir
            self.window.destroy()
            self.callback(u)
        else:
            self.lbl_erro.config(text="Usuário ou senha incorretos!")
            self.ent_pass.delete(0, tk.END)

    # ─────────────────────────────────────────────
    def janela_recuperar_senha(self):
        jan = tk.Toplevel(self.window)
        jan.title("Recuperar Senha")
        jan.geometry("440x300")
        jan.configure(bg="#f0f0f0")
        jan.resizable(False, False)
        jan.grab_set()
        jan.update_idletasks()
        sw = jan.winfo_screenwidth(); sh = jan.winfo_screenheight()
        jan.geometry(f"440x300+{(sw-440)//2}+{(sh-300)//2}")

        tk.Label(jan, text="🔑 Recuperação de Senha", font=("Arial", 13, "bold"),
                 bg="#f0f0f0", fg="#1a3a6c").pack(pady=(18, 4))
        tk.Label(jan,
                 text="Informe seu usuário.\nUma senha temporária será enviada ao e-mail cadastrado.",
                 bg="#f0f0f0", font=("Arial", 9), justify="center").pack(pady=(0, 12))

        frm = tk.Frame(jan, bg="#f0f0f0", padx=30); frm.pack(fill="x")
        tk.Label(frm, text="Usuário:", bg="#f0f0f0", font=("Arial", 10, "bold")).pack(anchor="w")
        ent_u = ttk.Entry(frm, width=32, font=("Arial", 11)); ent_u.pack(fill="x", pady=(2, 10))
        ent_u.focus()

        lbl_res = tk.Label(jan, text="", bg="#f0f0f0", font=("Arial", 9, "bold"),
                           wraplength=380, justify="center")
        lbl_res.pack(pady=4)

        def enviar():
            u = ent_u.get().strip()
            if not u:
                lbl_res.config(text="Informe o usuário!", fg="#721c24"); return
            import sqlite3 as _sq
            conn = _sq.connect(DB_FILE)
            row = conn.execute("SELECT email FROM usuarios_sistema WHERE usuario=?", (u,)).fetchone()
            conn.close()
            if not row:
                lbl_res.config(text="Usuário não encontrado!", fg="#721c24"); return
            email = row[0]
            if not email or "@" not in email:
                lbl_res.config(
                    text="Nenhum e-mail cadastrado para este usuário.\n"
                         "Use o login master (admin) para redefinir.",
                    fg="#856404"); return
            senha_temp = gerar_senha_temporaria()
            ok, msg = enviar_email_recuperacao(email, u, senha_temp)
            if ok:
                import sqlite3 as _sq2
                conn2 = _sq2.connect(DB_FILE)
                conn2.execute("UPDATE usuarios_sistema SET senha_hash=? WHERE usuario=?",
                              (hash_senha(senha_temp), u))
                conn2.commit(); conn2.close()
                # Mascarar e-mail: jo***@gmail.com
                partes = email.split("@")
                mascara = partes[0][:2] + "***@" + partes[1]
                lbl_res.config(fg="#1e5631",
                    text=f"✅ Senha temporária enviada para {mascara}.\n"
                         "Use-a para entrar e altere sua senha em seguida.")
            else:
                lbl_res.config(text=f"❌ {msg}", fg="#721c24")

        tk.Button(frm, text="📧 ENVIAR SENHA TEMPORÁRIA", bg="#1a3a6c", fg="white",
                  font=("Arial", 10, "bold"), relief="flat", padx=12, pady=8,
                  cursor="hand2", command=enviar).pack(fill="x")

        tk.Label(jan,
                 text="💡 Dica: se não tiver acesso ao e-mail, use o usuário 'admin'\n"
                                "(Contate o suporte - (74) 9 9927-7468)",
                 bg="#f0f0f0", fg="#888", font=("Arial", 8, "italic"),
                 justify="center").pack(pady=(10, 0))


if __name__ == "__main__":
    inicializar_banco_global()
    root = tk.Tk()
    root.withdraw()

    def iniciar_sistema(usuario="sistema"):
        # Destroi qualquer widget residual no root antes de construir
        for widget in root.winfo_children():
            try:
                widget.destroy()
            except Exception:
                pass
        root.deiconify()
        root.update()
        TechPrimePlus(root, usuario_logado=usuario)

    def apos_licenca():
        JanelaLogin(root, iniciar_sistema)

    # Usa ler_licenca_arquivo() que valida HWID + chave + assinatura
    if ler_licenca_arquivo():
        JanelaLogin(root, iniciar_sistema)
    else:
        JanelaLicenca(root, apos_licenca)

    root.mainloop()