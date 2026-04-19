"""pages/chatbot.py — Assistant IA Finalyse (Français)"""
import json, os, urllib.request
from urllib import error as ue
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QScrollArea, QPushButton, QLineEdit,
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, pyqtSlot, QTimer
from PyQt6.QtGui import QCursor
from theme import C, PrimaryButton, shadow

# Lire la configuration depuis les variables d'environnement (pas hardcodes)
OLLAMA_URL   = os.getenv("OLLAMA_URL",   "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")


class OllamaCheckWorker(QThread):
    result = pyqtSignal(bool)
    def run(self):
        try:
            req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as r:
                self.result.emit(r.status == 200)
        except Exception:
            self.result.emit(False)


class ChatWorker(QThread):
    reply = pyqtSignal(str)
    error = pyqtSignal(str)
    def __init__(self, message, historique, context):
        super().__init__(); self._msg=message; self._hist=historique; self._ctx=context

    def run(self):
        resp = self._call_ollama()
        if resp: self.reply.emit(resp); return
        resp = self._call_backend()
        if resp: self.reply.emit(resp); return
        self.reply.emit(self._fallback())

    def _call_ollama(self):
        ctx=self._ctx
        system=(
            "Tu es l'assistant IA de Finalyse. Tu réponds en français, "
            "de façon concise et professionnelle.\n\n"
            f"Données : dépenses={ctx.get('total_depenses',0):,.0f} FCFA, "
            f"factures={ctx.get('nb_factures',0)}, anomalies={ctx.get('nb_anomalies',0)}"
        )
        msgs=[{"role":"system","content":system}]
        for m in self._hist[-6:]: msgs.append({"role":m["role"],"content":m["content"]})
        msgs.append({"role":"user","content":self._msg})
        payload=json.dumps({"model":OLLAMA_MODEL,"messages":msgs,"stream":False,
                             "options":{"temperature":0.6,"num_predict":512}}).encode()
        try:
            req=urllib.request.Request(f"{OLLAMA_URL}/api/chat",data=payload,method="POST",
                                        headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                d=json.loads(r.read().decode())
                return (d.get("message",{}).get("content","") or d.get("response","")).strip()
        except Exception:
            return ""

    def _call_backend(self):
        try:
            from api_client import api
            return api.chat(self._msg, self._hist).get("response","")
        except Exception:
            return ""

    def _fallback(self):
        ctx=self._ctx; q=self._msg.lower()
        total=ctx.get("total_depenses",0); nb=ctx.get("nb_factures",0); anom=ctx.get("nb_anomalies",0)
        if any(w in q for w in ["total","dépense","montant","combien","coût"]):
            return f"Dépenses totales : {total:,.0f} FCFA ({nb} facture(s))."
        if any(w in q for w in ["anomalie","problème","alerte","erreur"]):
            return "Aucune anomalie détectée." if anom==0 else f"{anom} anomalie(s) — consultez la page Analyse IA."
        if any(w in q for w in ["bonjour","salut","aide","hello"]):
            return f"Bienvenue sur Finalyse. Vous avez {nb} facture(s) pour {total:,.0f} FCFA.\n(Mode basique — Ollama non démarré)"
        return f"Assistant Finalyse (mode basique)\n{nb} factures | {total:,.0f} FCFA | {anom} anomalie(s)"


class ContextWorker(QThread):
    done=pyqtSignal(dict); error=pyqtSignal(str)
    def run(self):
        try:
            from api_client import api
            s=api.dashboard(); t=s.get("totaux",{})
            self.done.emit({"total_depenses":t.get("total_ttc",0),"nb_factures":t.get("nb_total",0),
                            "nb_anomalies":s.get("nb_anomalies",0),"top_fournisseurs":s.get("fournisseurs",[])[:5]})
        except Exception as e:
            self.error.emit(str(e)); self.done.emit({})


class ChatbotPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._alive=True; self.setStyleSheet(f"background:{C['surface']};")
        self._hist=[]; self._context={}; self._worker=None; self._ws=[]
        root=QVBoxLayout(self); root.setContentsMargins(24,24,24,24); root.setSpacing(16)

        hdr=QHBoxLayout()
        title=QLabel("Assistant IA")
        title.setStyleSheet(f"font-size:24px;font-weight:800;color:{C['primary']};background:transparent;")
        hdr.addWidget(title); hdr.addStretch()
        self._badge=QLabel("Vérification du moteur IA...")
        self._badge.setStyleSheet(f"font-size:12px;color:{C['on_surf_var']};background:transparent;")
        hdr.addWidget(self._badge); root.addLayout(hdr)

        sub=QLabel("Posez vos questions sur vos factures — IA locale (Ollama) ou mode basique si Ollama n'est pas démarré.")
        sub.setStyleSheet(f"font-size:13px;color:{C['on_surf_var']};background:transparent;")
        root.addWidget(sub)

        self._scroll=QScrollArea()
        self._scroll.setWidgetResizable(True); self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setStyleSheet(f"background:{C['surf_lowest']};border-radius:12px;")
        shadow(self._scroll,blur=12,y=3,color=C["primary"],alpha=8)
        self._msgs_w=QWidget(); self._msgs_w.setStyleSheet(f"background:{C['surf_lowest']};")
        self._msgs_l=QVBoxLayout(self._msgs_w)
        self._msgs_l.setContentsMargins(20,20,20,20); self._msgs_l.setSpacing(10)
        self._msgs_l.addStretch(); self._scroll.setWidget(self._msgs_w)
        root.addWidget(self._scroll, 1)

        sug=QHBoxLayout(); sug.setSpacing(8)
        for txt in ["Total dépenses ?","Anomalies détectées ?","Mes fournisseurs ?","Conseils d'optimisation ?"]:
            b=QPushButton(txt)
            b.setStyleSheet(f"""
                QPushButton{{background:{C['primary_fixed']};color:{C['primary']};border:none;
                    border-radius:14px;padding:5px 14px;font-size:11px;font-weight:600;}}
                QPushButton:hover{{background:{C['primary']};color:white;}}
            """)
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.clicked.connect(lambda _,t=txt: self._send(t)); sug.addWidget(b)
        sug.addStretch(); root.addLayout(sug)

        inp_frame=QFrame()
        inp_frame.setStyleSheet(f"background:{C['surf_lowest']};border-radius:12px;border:none;")
        shadow(inp_frame,blur=12,y=3,color=C["primary"],alpha=8)
        il=QHBoxLayout(inp_frame); il.setContentsMargins(12,12,12,12); il.setSpacing(10)
        self._input=QLineEdit()
        self._input.setPlaceholderText("Posez une question sur vos factures...")
        self._input.setFixedHeight(48)
        self._input.setStyleSheet(f"""
            QLineEdit{{background:{C['surf_low']};border:none;border-radius:8px;
                padding:0 16px;font-size:13px;color:{C['on_surface']};font-family:"Segoe UI";}}
            QLineEdit:focus{{background:white;border:1.5px solid {C['primary']};}}
        """)
        self._input.returnPressed.connect(lambda: self._send(self._input.text()))
        il.addWidget(self._input)
        self._send_btn=PrimaryButton("➤")
        self._send_btn.setFixedSize(48, 48)
        self._send_btn.clicked.connect(lambda: self._send(self._input.text()))
        il.addWidget(self._send_btn); root.addWidget(inp_frame)

        self._load_context(); self._check_ollama()

    def _load_context(self):
        w=ContextWorker(); w.done.connect(lambda d: setattr(self,"_context",d))
        w.error.connect(lambda e: None); self._ws.append(w); w.start()

    def _check_ollama(self):
        w=OllamaCheckWorker(); w.result.connect(self._on_ollama); self._ws.append(w); w.start()

    @pyqtSlot(bool)
    def _on_ollama(self, ok: bool):
        if not self._alive: return
        # Vérifier aussi le statut DeepSeek via l'API
        try:
            from api_client import api
            status = api.chat_status()
            mode = status.get("mode", "local")
            if mode == "deepseek":
                self._badge.setText("IA DeepSeek (en ligne)")
                self._badge.setStyleSheet(f"font-size:12px;color:{C['secondary']};background:transparent;")
                self._add_bot("Bonjour ! Je suis l'assistant IA Finalyse propulsé par DeepSeek.\n\nJ'ai accès à toutes vos données financières. Posez-moi vos questions sur vos dépenses, recettes, fournisseurs ou anomalies.")
            elif mode == "ollama":
                self._badge.setText("IA Ollama (local)")
                self._badge.setStyleSheet(f"font-size:12px;color:{C['secondary']};background:transparent;")
                self._add_bot("Bonjour ! Je suis l'assistant IA Finalyse (Ollama local).\n\nJ'ai accès à toutes vos données financières. Posez-moi vos questions !")
            else:
                self._badge.setText("Mode basique (pas d'IA)")
                self._badge.setStyleSheet(f"font-size:12px;color:{C['on_surf_var']};background:transparent;")
                self._add_bot("Bonjour ! Je fonctionne en mode basique.\n\nPour activer l'IA complète :\n  • Ajoutez DEEPSEEK_API_KEY dans backend/.env (internet)\n  • Ou installez Ollama : ollama pull deepseek-r1:7b (local)\n\nJe peux quand même répondre à vos questions sur vos données !")
        except Exception:
            if ok:
                self._badge.setText("IA Ollama (local)")
                self._badge.setStyleSheet(f"font-size:12px;color:{C['secondary']};background:transparent;")
            else:
                self._badge.setText("Mode basique")
                self._badge.setStyleSheet(f"font-size:12px;color:{C['on_surf_var']};background:transparent;")
            self._add_bot("Bonjour ! Assistant IA Finalyse. Posez vos questions sur vos finances.")

    def _send(self, text: str):
        text=text.strip()
        if not text or not self._alive: return
        if self._worker and self._worker.isRunning(): return
        self._input.clear(); self._add_user(text); self._set_loading(True); self._add_typing()
        self._worker=ChatWorker(text, list(self._hist[-8:]), self._context)
        self._worker.reply.connect(self._on_reply); self._worker.error.connect(self._on_err)
        self._worker.start(); self._hist.append({"role":"user","content":text})

    @pyqtSlot(str)
    def _on_reply(self, resp: str):
        if not self._alive: return
        self._remove_typing(); self._add_bot(resp)
        self._hist.append({"role":"assistant","content":resp}); self._set_loading(False)

    @pyqtSlot(str)
    def _on_err(self, msg: str):
        if not self._alive: return
        self._remove_typing()
        self._add_bot(f"Erreur : {msg}\n\nVérifiez que le serveur est démarré.")
        self._set_loading(False)

    def _set_loading(self, v: bool):
        if not self._alive: return
        self._send_btn.setEnabled(not v)
        self._input.setEnabled(not v)
        if v:
            # Spinner animé sur le bouton
            self._spin_step = 0
            self._spin_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
            if not hasattr(self, "_spin_timer"):
                self._spin_timer = QTimer(self)
                self._spin_timer.timeout.connect(self._tick_spin)
            self._spin_timer.start(80)
        else:
            if hasattr(self, "_spin_timer"):
                self._spin_timer.stop()
            self._send_btn.setText("➤")

    def _tick_spin(self):
        if not self._alive: return
        self._spin_step = (self._spin_step + 1) % len(self._spin_chars)
        self._send_btn.setText(self._spin_chars[self._spin_step])

    def _add_user(self, text):
        if not self._alive: return
        self._msgs_l.insertWidget(self._msgs_l.count()-1, self._bubble(text, user=True))
        self._scroll_bot()

    def _add_bot(self, text):
        if not self._alive: return
        self._msgs_l.insertWidget(self._msgs_l.count()-1, self._bubble(text, user=False))
        self._scroll_bot()

    def _add_typing(self):
        if not self._alive: return
        row = QWidget(); row._typing = True
        rl = QHBoxLayout(row); rl.setContentsMargins(0, 0, 0, 0)
        b = QFrame()
        b.setStyleSheet(f"background:{C['surf_low']};border-radius:12px 12px 12px 4px;border:none;")
        bl = QVBoxLayout(b); bl.setContentsMargins(14, 10, 14, 10)
        self._typing_lbl = QLabel("●  ●  ●")
        self._typing_lbl.setStyleSheet(f"font-size:16px;color:{C['primary']};background:transparent;letter-spacing:4px;")
        # Animer les points
        self._typing_step = 0
        self._typing_frames = ["●  ○  ○", "○  ●  ○", "○  ○  ●", "○  ●  ○"]
        if not hasattr(self, "_typing_timer"):
            self._typing_timer = QTimer(self)
            self._typing_timer.timeout.connect(self._tick_typing)
        self._typing_timer.start(300)
        bl.addWidget(self._typing_lbl)
        rl.addWidget(b); rl.addStretch()
        self._msgs_l.insertWidget(self._msgs_l.count() - 1, row)
        self._scroll_bot()

    def _tick_typing(self):
        if not self._alive or not hasattr(self, "_typing_lbl"): return
        try:
            self._typing_step = (self._typing_step + 1) % len(self._typing_frames)
            self._typing_lbl.setText(self._typing_frames[self._typing_step])
        except RuntimeError:
            self._typing_timer.stop()

    def _remove_typing(self):
        if hasattr(self, "_typing_timer"):
            self._typing_timer.stop()
        for i in range(self._msgs_l.count()-1, -1, -1):
            it = self._msgs_l.itemAt(i)
            if it and it.widget() and getattr(it.widget(), "_typing", False):
                self._msgs_l.takeAt(i).widget().deleteLater()
                break

    def _bubble(self, text: str, user: bool) -> QWidget:
        row=QWidget(); rl=QHBoxLayout(row); rl.setContentsMargins(0,0,0,0)
        if user: rl.addStretch()
        b=QFrame()
        if user:
            b.setStyleSheet(f"background:{C['primary']};border-radius:12px 12px 4px 12px;border:none;")
        else:
            b.setStyleSheet(f"background:{C['surf_low']};border-radius:12px 12px 12px 4px;border:none;")
        bl=QVBoxLayout(b); bl.setContentsMargins(14,10,14,10)
        lbl=QLabel(text); lbl.setWordWrap(True); lbl.setMaximumWidth(480)
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl.setStyleSheet(
            "font-size:13px;color:white;background:transparent;" if user
            else f"font-size:13px;color:{C['on_surface']};background:transparent;"
        )
        bl.addWidget(lbl); rl.addWidget(b)
        if not user: rl.addStretch()
        return row

    def _scroll_bot(self):
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))

    def closeEvent(self, e):
        self._alive=False; super().closeEvent(e)
