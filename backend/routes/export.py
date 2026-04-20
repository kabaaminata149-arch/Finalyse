"""routes/export.py — Export CSV, PDF, rapport email"""
import os, smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr

import database.db as db
from auth.jwt_handler import current_user
from services.export_service import export_csv, export_pdf

router = APIRouter(prefix="/api/export", tags=["Export"])


@router.get("/bilan")
def bilan_export(
    periode: str = Query("", description="Période ex: Mars 2024"),
    p:       dict = Depends(current_user),
):
    """Retourne un bilan financier texte (utilisé par le chatbot et l'API)."""
    raw_stats  = db.get_stats(p["uid"])
    from services.processor import generate_bilan
    return {"bilan": generate_bilan(raw_stats, periode), "stats": raw_stats}


@router.get("/csv")
def csv_export(p: dict = Depends(current_user)):
    factures = db.get_factures(p["uid"], limit=1000)
    path     = export_csv(factures, p["uid"])
    return FileResponse(path, filename=os.path.basename(path), media_type="text/csv")


@router.get("/pdf")
def pdf_export(
    periode:    str = Query("", description="Période ex: Mars 2024"),
    annee:      int = Query(0),
    mois:       int = Query(0),
    dossier_id: int = Query(0),
    p:          dict = Depends(current_user),
):
    annee_f   = annee      if annee      else None
    mois_f    = mois       if mois       else None
    dossier_f = dossier_id if dossier_id else None

    # Récupérer les factures filtrées par dossier
    factures  = db.get_factures(p["uid"], limit=1000, annee=annee_f, mois=mois_f, dossier_id=dossier_f)
    raw_stats = db.get_stats(p["uid"], annee=annee_f, mois=mois_f, dossier_id=dossier_f)
    user      = db.get_user_id(p["uid"])

    # Nom de l'entreprise + nom du dossier pour l'en-tête du rapport
    entreprise = user.get("nom", "Mon Entreprise") if user else "Mon Entreprise"
    if dossier_f:
        dossier = db.get_dossier(dossier_f, p["uid"])
        if dossier:
            dossier_nom = dossier.get("nom", "")
            entreprise  = f"{entreprise} — {dossier_nom}" if entreprise else dossier_nom

    flux = raw_stats.get("flux", {})
    stats = {
        "total_depenses":  flux.get("depenses_ttc", 0),
        "total_recettes":  flux.get("recettes_ttc", 0),
        "solde_net":       flux.get("solde_net", 0),
        "total_ht":        raw_stats.get("totaux", {}).get("total_ht", 0),
        "total_tva":       raw_stats.get("totaux", {}).get("total_tva", 0),
        "nb_traitees":     raw_stats.get("totaux", {}).get("nb_traites", 0),
        "nb_anomalies":    raw_stats.get("nb_anomalies", 0),
    }

    import logging
    logging.getLogger("export").info(
        "[PDF] uid=%d dossier_id=%s nb_factures=%d dep=%.0f",
        p["uid"], dossier_f, len(factures), stats["total_depenses"]
    )

    path = export_pdf(factures, p["uid"], periode, stats, entreprise)

    if not os.path.exists(path) or os.path.getsize(path) == 0:
        raise HTTPException(500, "Erreur lors de la génération du rapport.")

    media = "application/pdf" if path.endswith(".pdf") else "text/plain"
    return FileResponse(
        path,
        filename=os.path.basename(path),
        media_type=media,
        headers={"Cache-Control": "no-cache"}
    )


class SendReportIn(BaseModel):
    to_email:   EmailStr
    to_name:    str = ""
    periode:    str = ""
    message:    str = ""
    dossier_id: int = 0


@router.post("/send-report")
def send_report(data: SendReportIn, p: dict = Depends(current_user)):
    # Recharger le .env pour s'assurer que les variables SMTP sont à jour
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)

    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASS", "").strip()
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))

    if not smtp_user or not smtp_pass:
        raise HTTPException(400,
            "SMTP non configuré. Ajoutez SMTP_USER et SMTP_PASS dans backend/.env puis redémarrez GO.py.")

    # Générer le PDF filtré par dossier si sélectionné
    dossier_f  = data.dossier_id if data.dossier_id else None
    factures   = db.get_factures(p["uid"], limit=1000, dossier_id=dossier_f)
    raw_stats  = db.get_stats(p["uid"], dossier_id=dossier_f)
    user       = db.get_user_id(p["uid"])
    entreprise = user.get("nom", "") if user else ""
    if dossier_f:
        dossier = db.get_dossier(dossier_f, p["uid"])
        if dossier:
            dossier_nom = dossier.get("nom", "")
            entreprise  = f"{entreprise} — {dossier_nom}" if entreprise else dossier_nom
    flux = raw_stats.get("flux", {})
    stats_flat = {
        "total_depenses": flux.get("depenses_ttc", 0),
        "total_recettes": flux.get("recettes_ttc", 0),
        "solde_net":      flux.get("solde_net", 0),
        "total_ht":       raw_stats.get("totaux", {}).get("total_ht", 0),
        "total_tva":      raw_stats.get("totaux", {}).get("total_tva", 0),
        "nb_traitees":    raw_stats.get("totaux", {}).get("nb_traites", 0),
        "nb_anomalies":   raw_stats.get("nb_anomalies", 0),
    }
    pdf_path   = export_pdf(factures, p["uid"], data.periode, stats_flat, entreprise)
    tot        = raw_stats.get("totaux", {})
    flux_data  = raw_stats.get("flux", {})

    # Construire l'email HTML
    msg = MIMEMultipart("mixed")
    msg["From"]    = f"Finalyse <{smtp_user}>"
    msg["To"]      = f"{data.to_name} <{data.to_email}>" if data.to_name else data.to_email
    msg["Subject"] = f"Finalyse — Rapport {data.periode or datetime.now().strftime('%B %Y')}"

    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:auto">
      <div style="background:#000666;color:white;padding:32px;border-radius:12px 12px 0 0">
        <h1 style="margin:0;font-size:24px">Finalyse</h1>
        <p style="margin:4px 0 0;opacity:.7">Rapport {data.periode}</p>
      </div>
      <div style="padding:24px;background:#f8f9fa">
        <p>Bonjour <strong>{data.to_name or (user.get('nom','') if user else '')}</strong>,</p>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin:20px 0">
          <div style="background:white;padding:16px;border-radius:8px;text-align:center">
            <div style="font-size:11px;color:#666">DEPENSES TTC</div>
            <div style="font-size:18px;font-weight:700;color:#b3261e">{flux_data.get('depenses_ttc', 0):,.0f} FCFA</div>
          </div>
          <div style="background:white;padding:16px;border-radius:8px;text-align:center">
            <div style="font-size:11px;color:#666">RECETTES TTC</div>
            <div style="font-size:18px;font-weight:700;color:#1b6d24">{flux_data.get('recettes_ttc', 0):,.0f} FCFA</div>
          </div>
          <div style="background:white;padding:16px;border-radius:8px;text-align:center">
            <div style="font-size:11px;color:#666">SOLDE NET</div>
            <div style="font-size:18px;font-weight:700;color:#000666">{flux_data.get('solde_net', 0):+,.0f} FCFA</div>
          </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:12px 0">
          <div style="background:white;padding:12px;border-radius:8px;text-align:center">
            <div style="font-size:11px;color:#666">FACTURES TRAITEES</div>
            <div style="font-size:20px;font-weight:700;color:#000666">{tot.get('nb_traites', 0)}</div>
          </div>
          <div style="background:white;padding:12px;border-radius:8px;text-align:center">
            <div style="font-size:11px;color:#666">ANOMALIES</div>
            <div style="font-size:20px;font-weight:700;color:#f57c00">{raw_stats.get('nb_anomalies', 0)}</div>
          </div>
        </div>
        {f"<p>{data.message}</p>" if data.message else ""}
        <p style="color:#666;font-size:13px">Le rapport complet est joint en PDF.</p>
      </div>
      <div style="background:#eee;padding:12px;text-align:center;font-size:11px;color:#999;border-radius:0 0 12px 12px">
        Finalyse &copy; {datetime.now().year}
      </div>
    </div>
    """
    msg.attach(MIMEText(html, "html", "utf-8"))

    # Joindre le PDF
    if os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            att = MIMEApplication(f.read(), Name=os.path.basename(pdf_path))
            att["Content-Disposition"] = f'attachment; filename="{os.path.basename(pdf_path)}"'
            msg.attach(att)

    # Envoyer
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.ehlo(); server.starttls(); server.ehlo()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, data.to_email, msg.as_string())
        return {"message": f"Rapport envoyé à {data.to_email}"}
    except smtplib.SMTPAuthenticationError:
        raise HTTPException(500,
            "Authentification Gmail échouée. Utilisez un mot de passe d'application "
            "(myaccount.google.com/apppasswords)")
    except smtplib.SMTPException as e:
        raise HTTPException(500, f"Erreur SMTP : {e}")
    except Exception as e:
        raise HTTPException(500, f"Erreur envoi : {e}")
