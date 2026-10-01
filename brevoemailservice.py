import os
from flask_mail import Message
from flask import current_app

def send_otp_email(mail, to_email, fname, otp_code):
    """
    Sends a styled 6-digit OTP verification email via Brevo / Flask-Mail.
    
    :param mail: Flask-Mail Mail instance
    :param to_email: Recipient's email address
    :param fname: Recipient's first name
    :param otp_code: 6-digit numeric OTP code
    :return: tuple (success: bool, error: str or None)
    """
    try:
        sender = (
            current_app.config.get('MAIL_DEFAULT_SENDER')
            or os.getenv('MAIL_DEFAULT_SENDER')
            or os.getenv('MAIL_USERNAME')
            or "noreply@smartfinancemanager.com"
        )
        
        msg = Message(
            subject=f"{otp_code} is your Smart Finance Manager verification code",
            sender=sender,
            recipients=[to_email]
        )
        
        msg.body = (
            f"Hello {fname},\n\n"
            f"Your 6-digit verification code for Smart Finance Manager is: {otp_code}\n\n"
            f"This code will expire in 10 minutes.\n\n"
            f"If you did not request this, please ignore this email."
        )
        
        msg.html = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0f1015; color: #e1e3ec; margin: 0; padding: 24px; }}
            .card {{ max-width: 500px; margin: 0 auto; background: #161722; border: 1px solid rgba(187, 134, 252, 0.25); border-radius: 16px; padding: 36px 28px; box-shadow: 0 16px 40px rgba(0,0,0,0.6); }}
            .brand {{ text-align: center; margin-bottom: 24px; }}
            .brand-title {{ font-size: 22px; font-weight: 800; background: linear-gradient(135deg, #bb86fc, #03dac6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
            .heading {{ color: #ffffff; font-size: 20px; font-weight: 700; text-align: center; margin: 12px 0 20px; }}
            .otp-container {{ background: rgba(3, 218, 198, 0.08); border: 1.5px dashed #03dac6; border-radius: 12px; padding: 20px; text-align: center; margin: 28px 0; }}
            .otp-code {{ font-size: 38px; font-weight: 800; letter-spacing: 10px; color: #03dac6; font-family: monospace; }}
            .note {{ font-size: 13px; color: #9496a8; text-align: center; line-height: 1.5; }}
            .footer {{ border-top: 1px solid rgba(255, 255, 255, 0.08); margin-top: 28px; padding-top: 20px; font-size: 11px; color: #696b7d; text-align: center; }}
          </style>
        </head>
        <body>
          <div class="card">
            <div class="brand">
              <span class="brand-title">Smart Finance Manager</span>
              <div class="heading">Verify Your Email Address</div>
            </div>
            <p style="font-size: 15px; margin: 0 0 12px; color: #cfd2e3;">Hello <strong>{fname}</strong>,</p>
            <p style="font-size: 14px; margin: 0 0 20px; color: #a1a4b8; line-height: 1.6;">
              Please use the 6-digit verification code below to activate your Smart Finance Manager account.
            </p>
            <div class="otp-container">
              <div class="otp-code">{otp_code}</div>
            </div>
            <p class="note">
              ⏳ This code is valid for <strong>10 minutes</strong>.<br>
              If you did not create an account with us, you can safely ignore this email.
            </p>
            <div class="footer">
              &copy; 2026 Smart Finance Manager. All rights reserved.
            </div>
          </div>
        </body>
        </html>
        """
        
        mail.send(msg)
        print(f" Verification email successfully sent to {to_email}")
        return True, None
    except Exception as e:
        print(f" Failed to send verification email to {to_email}: {e}")
        return False, str(e)
