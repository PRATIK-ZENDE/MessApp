# Mess Management System

A complete Flask-based mess management system with student attendance tracking, billing, and UPI payment integration.

## 🔒 Security Setup (IMPORTANT!)

### First Time Setup

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment Variables**
   - Copy `.env.example` to `.env`
   - Generate new secret keys:
     ```bash
     python -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32)); print('WTF_CSRF_SECRET_KEY=' + secrets.token_hex(32))"
     ```
   - Update `.env` with the generated keys
   - Configure your UPI details (optional - can be set in Settings page later)

3. **Run the Application**
   ```bash
   python app.py
   ```
   Or use the provided batch file:
   ```bash
   run.bat
   ```

## ⚙️ Configuration

All sensitive configuration is stored in `.env` file:

- `SECRET_KEY` - Flask session encryption key
- `WTF_CSRF_SECRET_KEY` - CSRF protection key
- `DATABASE_URL` - Database connection string
- `UPI_ID` - UPI payment ID (optional)
- `UPI_NAME` - Business name for UPI (optional)

**⚠️ NEVER commit the `.env` file to version control!**

## 🚀 Features

- **Multi-Mess Support** - Each mess operates independently
- **Student Management** - Add, edit, delete students with auto-generated roll numbers
- **Attendance Tracking** - QR code scanning and manual attendance
- **Billing System** - Automatic bill generation based on attendance
- **Payment Management** - UPI integration with QR codes and deep links
- **Admin Controls** - Password management, settings configuration
- **Security** - CSRF protection, password hashing, session management

## 🗒️ To-Do

- Implement email-based forgot password flow using expiring reset tokens

## 🌐 Deployment Checklist

1. **Choose a Host**: Render, Railway, or Fly.io offer free tiers capable of running this Flask + Gunicorn app.
2. **Configure Environment**: set `SECRET_KEY`, `WTF_CSRF_SECRET_KEY`, and `DATABASE_URL` in the platform dashboard; for production, point `DATABASE_URL` to a managed Postgres instance.
3. **Install Dependencies**: the production requirement list now includes Gunicorn, so the host's build step can install it automatically.
4. **Start Command**: the provided `Procfile` defines `web: gunicorn app:app`; most platforms detect and use it without extra settings.
5. **Migrate Database**: run the migration helpers against the live database, then create an initial admin and mess record.
6. **Smoke Test**: verify admin login, student onboarding, QR attendance, billing, and payment flows after each deploy.

## 📁 Project Structure

```
Mess App/
├── app.py                      # Main application
├── requirements.txt            # Python dependencies
├── .env                        # Environment variables (SECRET!)
├── .env.example               # Environment template
├── .gitignore                 # Git ignore rules
├── templates/                 # HTML templates
├── static/                    # CSS, JS, images
├── instance/                  # Database (auto-created)
└── migrate_*.py              # Database migration scripts
```

## 🔐 Security Features

1. **Environment-based secrets** - No hardcoded passwords
2. **CSRF protection** - All forms protected
3. **Password hashing** - Werkzeug secure hashing
4. **Session security** - Flask-Login integration
5. **Multi-tenant isolation** - Mess-scoped queries
6. **Input validation** - Server-side validation on all inputs

## 📝 Admin Access

After first run, a default admin account is created:
- Username: `admin`
- Password: `admin123`

**⚠️ Change this immediately in Profile > Change Password**

## 🆘 Support

For issues or questions, please check the code comments or create an issue in the repository.

## 📜 License

This project is for educational purposes.
