# smart_attendance_with_profile.py
# FULLY FIXED VERSION – Camera + Persistent Login + Face Register

import os
import cv2
import csv
import datetime
import pickle
import cv2
import time
from flask import Flask, render_template_string, request, redirect, url_for, session, Response
from werkzeug.security import generate_password_hash, check_password_hash
import re


def strong_password(pw):
    if len(pw) < 8:
        return False
    if not re.search(r"[A-Z]", pw):   # Uppercase
        return False
    if not re.search(r"[a-z]", pw):   # Lowercase
        return False
    if not re.search(r"[0-9]", pw):   # Number
        return False
    if not re.search(r"[!@#$%^&*()_+=\-{}[\]:;\"'<>,.?/]", pw):  # Special char
        return False
    return True

# ================== BASIC SETUP ==================
app = Flask(__name__)
app.secret_key = "attendance-secret-key"

DATA_DIR = "data"
FACE_DIR = os.path.join(DATA_DIR, "faces")
ATT_CSV = os.path.join(DATA_DIR, "attendance.csv")
USERS_FILE = os.path.join(DATA_DIR, "users.pkl")

os.makedirs(FACE_DIR, exist_ok=True)

# ================== LOAD / SAVE USERS ==================
if os.path.exists(USERS_FILE):
    with open(USERS_FILE, "rb") as f:
        USERS = pickle.load(f)
else:
    USERS = {}

def save_users():
    with open(USERS_FILE, "wb") as f:
        pickle.dump(USERS, f)

# ================== OPENCV ==================
eye_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + 'haarcascade_eye.xml'
)
face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
)

# ================== HTML ==================
BASE_STYLE = """
<style>
body{font-family:Arial;background:#0f172a;color:#e5e7eb;margin:0}
.nav{padding:12px 20px;background:#020617;display:flex;justify-content:space-between}
.card{max-width:420px;margin:40px auto;background:#020617;padding:20px;border-radius:14px}

input{
    width:100%;
    padding:10px;
    margin:8px 0;
    border-radius:10px;
    border:none;
    background:#ffffff;
    color:#020617;
    font-size:15px;
}
input::placeholder{
    color:#6b7280;
}

button{
    width:100%;
    padding:10px;
    margin:8px 0;
    border-radius:10px;
    border:none;
    background:#22c55e;
    font-weight:bold;
    cursor:pointer;
}

.profile{display:flex;gap:14px;align-items:center}
.avatar{width:72px;height:72px;border-radius:50%;background:#1e293b;
display:flex;align-items:center;justify-content:center;font-size:28px}
</style>
"""

LOGIN_HTML = BASE_STYLE + """
<div class='card'>
<h3>Login</h3>
<form method='post'>
<input type="text" name="user" placeholder="Username" required>
<input type="password" name="pw" placeholder="Password" required>
<button>Login</button>
</form>
<p>New? <a href='/register'>Register</a></p>
</div>
"""


REGISTER_HTML = BASE_STYLE + """
<div class='card'>
<h3>Register</h3>

{% if error %}
<p style="color:#f87171;font-size:14px;">{{ error }}</p>
{% endif %}

<form method='post'>
<input type="text" name="user" placeholder="Username" required>
<input type="email" name="email" placeholder="Email" required>
<input type="password" name="pw" placeholder="Password" required>
<button>Create</button>
</form>

<p style="font-size:12px;color:#9ca3af">
Password must contain 8+ characters with uppercase, lowercase, number & symbol
</p>
</div>
"""

DASH_HTML = BASE_STYLE + """
<div class='nav'>
<div class='profile'>
<div class='avatar'>{{user[0]|upper}}</div>
<div><b>{{user}}</b><br><small>{{email}}</small></div>
</div>
<a href='/logout'>Logout</a>
</div>
<div class='card'>
<a href='/register_face'><button>Register Face</button></a>
<a href='/attendance'><button>Mark Attendance</button></a>
</div>
"""

CAM_HTML = BASE_STYLE + """
<div class='card' style="text-align:center">
<img src="/video_feed" style="width:100%;border:2px solid #22c55e;border-radius:12px">
<p>{{hint}}</p>
</div>
"""

# ================== CAMERA ==================
def gen_frames(mode="register", username=None):
    camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)

    if not camera.isOpened():
        print("CAMERA NOT OPENED")
        return

    blink_start = None
    blink_done = False
    saved = False

    while True:
        success, frame = camera.read()
        if not success:
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.2, 4)

        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)

            roi_gray = gray[y:y+h, x:x+w]
            eyes = eye_cascade.detectMultiScale(roi_gray, 1.1, 8)

            # ---------------- BLINK DETECTION ----------------
            if len(eyes) == 0:
                if blink_start is None:
                    blink_start = time.time()

                elif time.time() - blink_start >= 0.4 and not blink_done:
                    blink_done = True

                    # 📸 Capture immediately
                    face_img = frame[y:y+h, x:x+w]
                    cv2.imwrite(f"registered_faces/{username}.jpg", face_img)
                    saved = True
            else:
                blink_start = None

            # ---------------- TEXT ----------------
            if not blink_done:
                cv2.putText(frame, "PLEASE BLINK",
                            (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.9, (0, 0, 255), 2)

            if saved:
                cv2.putText(frame, "REGISTRATION SUCCESSFUL",
                            (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.9, (0, 255, 0), 2)

        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


        

# ================== ROUTES ==================
@app.route('/', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        u,p = request.form['user'], request.form['pw']
        if u in USERS and check_password_hash(USERS[u]['pw'], p):
            session['u']=u
            return redirect('/dashboard')
    return render_template_string(LOGIN_HTML)

@app.route('/register', methods=['GET','POST'])
def register():
    error = None
    if request.method == 'POST':
        u = request.form['user']
        pw = request.form['pw']
        email = request.form['email']

        if not strong_password(pw):
            error = "Password must be 8+ chars with Upper, Lower, Number & Special character"
        elif u in USERS:
            error = "Username already exists"
        else:
            USERS[u] = {
                'email': email,
                'pw': generate_password_hash(pw)
            }
            save_users()
            return redirect('/')

    return render_template_string(REGISTER_HTML, error=error)


@app.route('/dashboard')
def dashboard():
    if 'u' not in session: return redirect('/')
    u = session['u']
    return render_template_string(DASH_HTML, user=u, email=USERS[u]['email'])

@app.route('/register_face')
def register_face():
    return render_template_string(CAM_HTML, hint="Look at camera")

@app.route('/attendance')
def attendance():
    if 'u' not in session: return redirect('/')
    with open(ATT_CSV,'a',newline='') as f:
        csv.writer(f).writerow([session['u'], datetime.datetime.now()])
    return "Attendance Saved"

@app.route('/video_feed')
def video_feed():
    username = session.get('u')
    return Response(
        gen_frames(mode="register", username=username),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=False, threaded=True)
