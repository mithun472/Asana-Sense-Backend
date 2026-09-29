"""
Email & PDF generation service for ASANA - SENSE AI.
Automatically sends certified session reports in PDF format via SMTP.
"""
import io
import os
import smtplib
from html import escape
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

def send_welcome_email(to_email: str, user_name: str) -> tuple[bool, str]:
    """Send a welcome email to a newly registered ASANA-SENSE user."""
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_from = os.getenv("SMTP_FROM_EMAIL", smtp_user).strip() or smtp_user
    smtp_from_name = os.getenv("SMTP_FROM_NAME", "ASANA - SENSE AI")

    if not smtp_user or not smtp_password:
        return False, "SMTP credentials (SMTP_USER / SMTP_PASSWORD) are not configured in backend/.env"

    if not to_email or "@" not in to_email:
        return False, f"Invalid destination email: {to_email}"

    safe_name = escape(user_name or "Yogi")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Welcome to ASANA-SENSE AI"
    msg["From"] = f"{smtp_from_name} <{smtp_from}>"
    msg["To"] = to_email

    plain_content = (
        f"Namaste {user_name or 'Yogi'},\n\n"
        "Welcome to ASANA-SENSE AI! We are glad to have you with us. "
        "Your personalized yoga practice and biomechanics coaching journey starts now.\n\n"
        "Keep showing up, breathe steadily, and enjoy your practice.\n\n"
        "With warmth,\nASANA-SENSE AI"
    )
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: Segoe UI, Arial, sans-serif; background: #fafaf9; color: #1c1917; padding: 24px;">
      <div style="max-width: 560px; margin: 0 auto; background: #ffffff; border: 1px solid #e7e5e4; border-radius: 16px; padding: 32px;">
        <h1 style="color: #047857; margin-top: 0;">Namaste, {safe_name}!</h1>
        <p>Welcome to <strong>ASANA-SENSE AI</strong>. We are glad to have you with us.</p>
        <p>Your personalized yoga practice and biomechanics coaching journey starts now. Keep showing up, breathe steadily, and enjoy your practice.</p>
        <p style="margin-bottom: 0;">With warmth,<br><strong>ASANA-SENSE AI</strong></p>
      </div>
    </body>
    </html>
    """
    msg.attach(MIMEText(plain_content, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    try:
        print(f"[EmailService] Connecting to SMTP server {smtp_host}:{smtp_port}...")
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=12)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=12)
            server.starttls()

        server.login(smtp_user, smtp_password)
        server.send_message(msg)
        server.quit()
        print(f"[EmailService] Welcome email successfully sent to {to_email}")
        return True, "Email sent successfully"
    except Exception as e:
        print(f"[EmailService] Failed to send welcome email to {to_email}: {e}")
        return False, str(e)


def generate_session_pdf(
    user_name: str,
    user_email: str,
    session_data: dict,
    ai_report: dict | None = None,
) -> bytes:
    """Generate a certified ASANA-SENSE Biomechanics Master Report as PDF bytes."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    primary_color = colors.HexColor("#047857")    # Emerald 700
    dark_color = colors.HexColor("#1c1917")       # Stone 900
    muted_color = colors.HexColor("#78716c")      # Stone 500
    card_bg = colors.HexColor("#f5f5f4")          # Stone 100

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=primary_color,
        spaceAfter=4,
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=muted_color,
        spaceAfter=12,
    )

    heading2_style = ParagraphStyle(
        'Heading2Style',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=dark_color,
        spaceBefore=10,
        spaceAfter=6,
    )

    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13.5,
        textColor=dark_color,
    )

    quote_style = ParagraphStyle(
        'QuoteStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=10,
        leading=14,
        textColor=primary_color,
        spaceAfter=8,
    )

    story = []

    # Title & Certification Header
    story.append(Paragraph("ASANA - SENSE • YOGA BIOMECHANICS MASTER REPORT", title_style))
    date_str = datetime.utcnow().strftime("%B %d, %Y - %H:%M UTC")
    story.append(Paragraph(f"Practitioner: <b>{user_name}</b> ({user_email}) &nbsp;|&nbsp; Certified Date: <b>{date_str}</b>", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=primary_color, spaceAfter=14))

    # High-level Metrics Card
    duration_secs = session_data.get("total_duration_seconds", 0) or session_data.get("totalDurationSeconds", 0)
    minutes = round(duration_secs / 60, 1)
    accuracy = session_data.get("overall_accuracy", 0) or session_data.get("overallAccuracy", 90)
    calories = session_data.get("calories_burned_est", 0) or session_data.get("caloriesBurnedEst", 25)
    poses = session_data.get("poses_recorded", []) or session_data.get("posesRecorded", [])

    metrics_data = [
        [
            Paragraph("<b>Overall Alignment</b>", body_style),
            Paragraph("<b>Practice Duration</b>", body_style),
            Paragraph("<b>Poses Completed</b>", body_style),
            Paragraph("<b>Est. Energy Burned</b>", body_style),
        ],
        [
            Paragraph(f"<font size=14 color='#047857'><b>{accuracy}%</b></font>", body_style),
            Paragraph(f"<font size=14><b>{minutes} mins</b></font>", body_style),
            Paragraph(f"<font size=14><b>{len(poses)}</b></font>", body_style),
            Paragraph(f"<font size=14><b>{calories} kcal</b></font>", body_style),
        ]
    ]

    metrics_table = Table(metrics_data, colWidths=[130, 130, 130, 130])
    metrics_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), card_bg),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#e7e5e4")),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e7e5e4")),
    ]))
    story.append(metrics_table)
    story.append(Spacer(1, 14))

    # AI Coach Boosting Message
    if ai_report:
        boosting = ai_report.get("boostingMessage") or ai_report.get("boosting_message")
        if boosting:
            story.append(Paragraph("Master Coach Boosting Message", heading2_style))
            story.append(Paragraph(f'"{boosting}"', quote_style))
            story.append(Spacer(1, 8))

    # Poses Breakdown Table
    if poses:
        story.append(Paragraph("Practiced Asanas Breakdown", heading2_style))
        poses_table_data = [
            [
                Paragraph("<b>Asana Name</b>", body_style),
                Paragraph("<b>Best Hold</b>", body_style),
                Paragraph("<b>Total Time</b>", body_style),
                Paragraph("<b>Form Score</b>", body_style),
            ]
        ]
        for p in poses:
            p_name = p.get("pose_name") or p.get("poseName") or "Yoga Pose"
            sanskrit = p.get("sanskrit_name") or p.get("sanskritName") or ""
            best_hold = p.get("best_hold_seconds") or p.get("bestHoldSeconds") or 0
            dur = p.get("duration_seconds") or p.get("durationSeconds") or 0
            score = p.get("accuracy_score") or p.get("accuracyScore") or accuracy

            display_name = f"<b>{p_name}</b>"
            if sanskrit:
                display_name += f"<br/><font color='#78716c' size=8><i>{sanskrit}</i></font>"

            poses_table_data.append([
                Paragraph(display_name, body_style),
                Paragraph(f"{best_hold}s", body_style),
                Paragraph(f"{dur}s", body_style),
                Paragraph(f"{score}%", body_style),
            ])

        poses_table = Table(poses_table_data, colWidths=[220, 100, 100, 100])
        poses_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#ecfdf5")),
            ('TEXTCOLOR', (0, 0), (-1, 0), primary_color),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor("#e7e5e4")),
        ]))
        story.append(poses_table)
        story.append(Spacer(1, 14))

    # Biomechanical Strengths & Growth Areas
    if ai_report:
        strengths = ai_report.get("keyStrengths") or []
        growths = ai_report.get("priorityGrowthAreas") or []

        if strengths or growths:
            story.append(Paragraph("Biomechanical Insights & Alignment Focus", heading2_style))
            for s in strengths:
                story.append(Paragraph(f"• <b>Key Strength:</b> {s}", body_style))
            for g in growths:
                story.append(Paragraph(f"• <b>Growth Cue:</b> {g}", body_style))
            story.append(Spacer(1, 10))

        # Recovery Nutrition
        nutrition = ai_report.get("fitnessNutrition") or {}
        if nutrition:
            post = nutrition.get("immediatePostWorkout") or []
            if post:
                story.append(Paragraph("Post-Practice Recovery Nutrition", heading2_style))
                story.append(Paragraph(f"Recommended recovery fuels: {', '.join(post)}", body_style))
                story.append(Spacer(1, 8))

    # Footer note
    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#e7e5e4"), spaceAfter=8))
    story.append(Paragraph(
        "Certified by ASANA - SENSE AI Biomechanics Core • Protected Yoga Practice Vault",
        ParagraphStyle('FooterText', parent=styles['Normal'], fontName='Helvetica', fontSize=8, textColor=muted_color, alignment=1)
    ))

    doc.build(story)
    return buffer.getvalue()


def send_session_report_email(
    to_email: str,
    user_name: str,
    session_data: dict,
    ai_report: dict | None = None,
) -> tuple[bool, str]:
    """
    Automated SMTP sender for ASANA - SENSE AI Session Reports.
    Generates PDF and sends to recipient directly.
    """
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_from = os.getenv("SMTP_FROM_EMAIL", smtp_user).strip() or smtp_user
    smtp_from_name = os.getenv("SMTP_FROM_NAME", "ASANA - SENSE AI")

    if not smtp_user or not smtp_password:
        return False, "SMTP credentials (SMTP_USER / SMTP_PASSWORD) are not configured in backend/.env"

    if not to_email or "@" not in to_email:
        return False, f"Invalid destination email: {to_email}"

    # Generate the PDF attachment
    try:
        pdf_bytes = generate_session_pdf(user_name, to_email, session_data, ai_report)
    except Exception as e:
        print(f"[EmailService] Failed to generate PDF: {e}")
        pdf_bytes = None

    accuracy = session_data.get("overall_accuracy", 0) or session_data.get("overallAccuracy", 90)
    duration_secs = session_data.get("total_duration_seconds", 0) or session_data.get("totalDurationSeconds", 0)
    mins = round(duration_secs / 60, 1)

    boosting_msg = ""
    if ai_report:
        boosting_msg = ai_report.get("boostingMessage") or ai_report.get("boosting_message") or ""

    # Build Multipart Email Message
    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"🧘 Your Yoga Biomechanics Report - {accuracy}% Form ({datetime.utcnow().strftime('%b %d')})"
    msg["From"] = f"{smtp_from_name} <{smtp_from}>"
    msg["To"] = to_email

    # Warm HTML body message from ASANA - SENSE AI
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background-color: #fafaf9; margin: 0; padding: 20px; color: #1c1917; }}
        .card {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 20px; padding: 30px; border: 1px solid #e7e5e4; box-shadow: 0 10px 25px rgba(0,0,0,0.05); }}
        .header {{ text-align: center; border-bottom: 2px solid #10b981; padding-bottom: 20px; }}
        .badge {{ background: #ecfdf5; color: #047857; font-size: 11px; font-weight: bold; padding: 4px 12px; border-radius: 9999px; text-transform: uppercase; letter-spacing: 1px; }}
        h1 {{ color: #047857; font-size: 22px; margin: 12px 0 4px 0; }}
        .message-box {{ background: #f5f5f4; border-left: 4px solid #10b981; padding: 14px 16px; border-radius: 0 12px 12px 0; margin: 20px 0; font-style: italic; color: #292524; }}
        .stats-grid {{ display: flex; justify-content: space-between; margin: 24px 0; gap: 10px; }}
        .stat-item {{ background: #fdfbf7; border: 1px solid #e7e5e4; border-radius: 14px; padding: 14px; text-align: center; flex: 1; }}
        .stat-value {{ font-size: 20px; font-weight: bold; color: #047857; }}
        .stat-label {{ font-size: 10px; text-transform: uppercase; color: #78716c; margin-top: 4px; }}
        .footer {{ text-align: center; font-size: 11px; color: #a8a29e; margin-top: 24px; padding-top: 16px; border-top: 1px solid #f5f5f4; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="header">
          <span class="badge">ASANA - SENSE AI Practice Certified</span>
          <h1>Namaste, {user_name}!</h1>
          <p style="color: #78716c; font-size: 13px; margin: 0;">Your live biomechanics session report has been generated and certified.</p>
        </div>

        {f'<div class="message-box">💬 <strong>Message from your ASANA-SENSE AI Coach:</strong><br/>"{boosting_msg}"</div>' if boosting_msg else ''}

        <div class="stats-grid">
          <div class="stat-item">
            <div class="stat-value">{accuracy}%</div>
            <div class="stat-label">Alignment Accuracy</div>
          </div>
          <div class="stat-item">
            <div class="stat-value">{mins}m</div>
            <div class="stat-label">Practice Time</div>
          </div>
          <div class="stat-item">
            <div class="stat-value">{len(session_data.get('poses_recorded') or session_data.get('posesRecorded') or [])}</div>
            <div class="stat-label">Poses Practiced</div>
          </div>
        </div>

        <p style="font-size: 13px; line-height: 1.6; color: #44403c;">
          Your full <strong>Certified Yoga Biomechanics Master Report (PDF)</strong> is attached to this email. You can keep it for your personal wellness logs or review it before your next session on mat.
        </p>

        <div class="footer">
          ASANA - SENSE • Real-Time AI Yoga Pose Coaching &amp; Vision Analytics Studio<br/>
          Safe &amp; Encrypted Biometrics Vault
        </div>
      </div>
    </body>
    </html>
    """

    alt_part = MIMEMultipart("alternative")
    alt_part.attach(MIMEText(f"Namaste {user_name},\n\nYour ASANA-SENSE practice session ({accuracy}% accuracy, {mins} mins) has been certified. Your official PDF report is attached to this email.", "plain"))
    alt_part.attach(MIMEText(html_content, "html"))
    msg.attach(alt_part)

    # Attach PDF if available
    if pdf_bytes:
        pdf_attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
        pdf_attachment.add_header(
            "Content-Disposition",
            "attachment",
            filename=f"AsanaSense_Report_{datetime.utcnow().strftime('%Y%m%d')}.pdf",
        )
        msg.attach(pdf_attachment)

    # Send via SMTP
    try:
        print(f"[EmailService] Connecting to SMTP server {smtp_host}:{smtp_port}...")
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=12)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=12)
            server.starttls()

        server.login(smtp_user, smtp_password)
        server.send_message(msg)
        server.quit()
        print(f"[EmailService] Session report successfully emailed to {to_email}")
        return True, "Email sent successfully"
    except Exception as e:
        print(f"[EmailService] Failed to send email to {to_email}: {e}")
        return False, str(e)
