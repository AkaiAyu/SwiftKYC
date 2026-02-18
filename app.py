# -------- IMPORTS --------
from flask import Flask, render_template, redirect, request, session
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from twilio.rest import Client
import os
import random
import requests

# -------- LOAD ENV --------
load_dotenv()

# -------- CREATE APP --------
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///database.db"
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20))
    status = db.Column(db.String(20), default="pending")

class DigiLockerUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    aadhaar = db.Column(db.String(12))
    mobile = db.Column(db.String(15))
    name = db.Column(db.String(50))
    dob = db.Column(db.String(20))
    pan = db.Column(db.String(20))

# -------- TWILIO CLIENT --------
twilio_client = Client(
    os.getenv("TWILIO_ACCOUNT_SID"),
    os.getenv("TWILIO_AUTH_TOKEN")
)

def send_otp_sms(phone, otp):
    message = twilio_client.messages.create(
        body=f"Your AI Bank OTP is: {otp}",
        from_=os.getenv("TWILIO_PHONE"),
        to=phone
    )
    print("OTP sent:", message.sid)

def calculate_risk_score():
    score = 0

    phone = session.get("phone")
    dl_id = session.get("dl_id")

    # 1️⃣ Check phone vs DigiLocker mobile match
    dl_user = DigiLockerUser.query.filter(
        (DigiLockerUser.aadhaar == dl_id) |
        (DigiLockerUser.mobile == dl_id)
    ).first()

    if dl_user and dl_user.mobile != phone:
        score += 25   # identity mismatch risk

    # 2️⃣ New account risk
    if session.get("new_user"):
        score += 10

    # 3️⃣ Simulated device risk
    device_risk = random.randint(5, 20)
    score += device_risk

    # 4️⃣ Simulated location risk
    location_risk = random.randint(5, 20)
    score += location_risk

    return score

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/signup")
def signup():
    session.clear()
    session["signup_mode"] = True
    return redirect("/register")

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        session["phone"] = request.form["phone"]
        return redirect("/send-otp")
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    # Clear previous session so old flags don't interfere
    session.clear()
    session["login_mode"] = True

    if request.method == "POST":
        phone = request.form["phone"]
        session["phone"] = phone
        return redirect("/send-otp")

    return render_template("login.html")

@app.route("/send-otp")
def send_otp():
    phone = session.get("phone")

    otp = str(random.randint(100000,999999))
    session["otp"] = otp

    send_otp_sms(phone, otp)

    return redirect("/verify-otp")

@app.route("/verify-otp", methods=["GET","POST"])
def verify_otp():
    if request.method == "POST":
        user_otp = request.form["otp"]

        if user_otp == session.get("otp"):
            phone = session.get("phone")
            existing_user = User.query.filter_by(phone=phone).first()

            # 🔐 LOGIN FLOW (existing user)
            if session.get("login_mode") and not session.get("signup_mode"):
                if not existing_user:
                    return "User not found. Please sign up first."

                # Check approval status
                if existing_user.status == "pending":
                    session.pop("login_mode", None)
                    return redirect("/under-review")

                if existing_user.status == "rejected":
                    return "Your application was rejected."

                # Approved user login
                session["logged_in"] = True
                session.pop("login_mode", None)
                return redirect("/dashboard")

            # 🆕 SIGNUP FLOW (new user)
            else:
                if not existing_user:
                    new_user = User(phone=phone, status="pending")
                    db.session.add(new_user)
                    db.session.commit()

                session["logged_in"] = True
                session["new_user"] = True
                return redirect("/digilocker")

        else:
            return "Invalid OTP"

    return render_template("otp.html")

@app.route("/digilocker")
def digilocker():
    if not session.get("logged_in"):
        return redirect("/register")
    return render_template("digilocker.html")

# ===== DigiLocker Login Step =====
@app.route("/digilocker-login", methods=["GET","POST"])
def digilocker_login():
    if request.method == "POST":
        dl_id = request.form["dl_id"]

        # Check DigiLocker DB
        user = DigiLockerUser.query.filter(
            (DigiLockerUser.aadhaar == dl_id) |
            (DigiLockerUser.mobile == dl_id)
        ).first()

        if not user:
            return "DigiLocker account not found."

        # 🔐 Generate DigiLocker OTP
        dl_otp = str(random.randint(100000,999999))
        session["dl_otp"] = dl_otp
        session["dl_id"] = dl_id

        print("DigiLocker OTP:", dl_otp)  # shows in terminal

        return redirect("/digilocker-otp")

    return render_template("digilocker_login.html")

# ===== DigiLocker OTP Step =====
@app.route("/digilocker-otp", methods=["GET","POST"])
def digilocker_otp():
    if request.method == "POST":
        entered_otp = request.form["otp"]

        if entered_otp == session.get("dl_otp"):
            return redirect("/consent")
        else:
            return "Invalid DigiLocker OTP"

    return render_template("digilocker_otp.html")

@app.route("/consent")
def consent():
    return render_template("consent.html")

@app.route("/fetch-kyc")
def fetch_kyc():
    dl_id = session.get("dl_id")

    # Find DigiLocker user in DB
    user = DigiLockerUser.query.filter(
        (DigiLockerUser.aadhaar == dl_id) |
        (DigiLockerUser.mobile == dl_id)
    ).first()

    # ❌ If not found → stop flow
    if not user:
        return "DigiLocker user not found. Please try again."

    # ✅ If found → fetch data
    session["name"] = user.name
    session["dob"] = user.dob
    session["pan"] = user.pan
    session["aadhaar"] = user.aadhaar

    return redirect("/kyc-form")

@app.route("/kyc-form")
def kyc_form():
    return render_template("kyc.html", data=session)

@app.route("/risk-check")
def risk_check():

    # If already calculated → show risk page again
    if session.get("risk_level"):
        return render_template(
            "risk.html",
            score=session["risk_score"],
            level=session["risk_level"]
        )

    # 🔢 Calculate risk
    score = calculate_risk_score()
    session["risk_score"] = score

    if score <= 30:
        session["risk_level"] = "LOW"

    elif score <= 60:
        session["risk_level"] = "MEDIUM"

    else:
        session["risk_level"] = "HIGH"

        # Save HIGH risk user as pending for admin review
        phone = session.get("phone")
        user = User.query.filter_by(phone=phone).first()
        if user:
            user.status = "pending"
            db.session.commit()

    # ✅ ALWAYS show risk page first (for all levels)
    session.pop("new_user", None)
    return render_template(
        "risk.html",
        score=session["risk_score"],
        level=session["risk_level"]
    )
            
@app.route("/extra-verification", methods=["GET","POST"])
def extra_verification():
    if request.method == "POST":
        entered_pan = request.form["pan"]
        entered_dob = request.form["dob"]

        dl_id = session.get("dl_id")

        user = DigiLockerUser.query.filter(
            (DigiLockerUser.aadhaar == dl_id) |
            (DigiLockerUser.mobile == dl_id)
        ).first()

        # ✅ Check PAN & DOB match
        if user and user.pan == entered_pan and user.dob == entered_dob:

            # 🎉 Mark user APPROVED (medium risk cleared)
            phone = session.get("phone")
            app_user = User.query.filter_by(phone=phone).first()
            if app_user:
                app_user.status = "approved"
                db.session.commit()

            # 👉 Go to services activation (NOT dashboard)
            return redirect("/activate-services")

        else:
            return "Verification failed. Details do not match."

    return render_template("extra_verification.html")

@app.route("/under-review")
def under_review():
    return render_template("under_review.html")

@app.route("/admin")
def admin():
    # Show only users waiting for review
    users = User.query.filter_by(status="pending").all()
    return render_template("admin.html", users=users)

@app.route("/approve/<int:user_id>")
def approve(user_id):
    user = User.query.get(user_id)
    user.status = "approved"
    db.session.commit()
    return redirect("/admin")

@app.route("/reject/<int:user_id>")
def reject(user_id):
    user = User.query.get(user_id)
    user.status = "rejected"
    db.session.commit()
    return redirect("/admin")

@app.route("/dashboard")
def dashboard():
    if not session.get("logged_in"):
        return redirect("/register")

    new_user = session.pop("new_user", False)
    return render_template("dashboard.html", new_user=new_user)

@app.route("/activate-services", methods=["GET","POST"])
def activate_services():
    if not session.get("logged_in"):
        return redirect("/login")

    # User clicked Activate
    if request.method == "POST":
        selected = request.form.getlist("services")
        session["services"] = selected

        return render_template("services_success.html", services=selected)

    # Just opened page
    return render_template("activate_services.html")

@app.route("/view-status")
def view_status():
    if not session.get("logged_in"):
        return redirect("/login")

    phone = session.get("phone")
    user = User.query.filter_by(phone=phone).first()

    # If admin approved → allow services activation
    if user and user.status == "approved":
        return redirect("/activate-services")

    # If admin rejected
    elif user and user.status == "rejected":
        return render_template("rejected.html")

    # Default = still pending review
    return render_template("high_risk_wait.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/reset-demo")
def reset_demo():
    User.query.delete()
    db.session.commit()
    return redirect("/admin")

@app.route("/chatbot", methods=["POST"])
def chatbot():
    user_msg = request.json["message"]

    prompt = f"""
    You are a friendly banking assistant for an AI Digital Bank.
    Answer briefly and clearly.

    User question: {user_msg}
    """

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
            "Content-Type": "application/json"
        },
        json={
            "model": "openrouter/auto",
            "messages": [{"role": "user", "content": prompt}]
        }
    )

    data = response.json()
    print("OpenRouter response:", data)   # 👈 helps debugging

    if "choices" not in data:
        return {"reply": "AI is busy right now 😅 Please try again."}

    reply = data["choices"][0]["message"]["content"]
    return {"reply": reply}

# -------- RUN APP --------
if __name__ == "__main__":
    app.run(debug=True)