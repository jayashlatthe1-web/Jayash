import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-change-in-production'
    DATABASE = 'sgu_bus.db'
    CURRENT_ACADEMIC_YEAR = '2024-2025'
    
    # Email configuration (replace with your SMTP settings)
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME') or 'your-email@gmail.com'
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD') or 'your-app-password'
    MAIL_DEFAULT_SENDER = 'SGU Bus Enrollment <noreply@sgu.edu>'
    
    # Razorpay configuration
    RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID') or 'rzp_test_kcaN9SvmjYUnhk'
    RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET') or 'nXRZts2xxH51aH7oIslz5m3F'
    RAZORPAY_WEBHOOK_SECRET = os.environ.get('RAZORPAY_WEBHOOK_SECRET') or 'your-webhook-secret'
    # If set to True, only show/use Razorpay payment option (hide UPI QR and instructions)
    RAZORPAY_ONLY = True
