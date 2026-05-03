from flask import Flask, render_template, request, redirect, session, send_file, flash, url_for, jsonify
import os, sqlite3, cv2, subprocess, json, time, shutil, glob
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from math import radians, cos, sin, asin, sqrt

app = Flask(__name__)
# 🔥 Session ko aur secure banane ke liye secret key
app.secret_key = "2027_ULTRA_SECURE_KEY"
otp_store = {}

COLLEGE_LAT, COLLEGE_LON, ALLOWED_RADIUS_KM = 29.1101, 76.1835, 3.0

def calculate_distance(lat1, lon1, lat2, lon2):
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon, dlat = lon2 - lon1, lat2 - lat1 
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    return 2 * asin(sqrt(a)) * 6371

def init_db():
    conn = sqlite3.connect("attendance.db")
    cursor = conn.cursor()

    cursor.execute("CREATE TABLE IF NOT EXISTS students(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, roll TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS attendance(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, roll TEXT, subject TEXT, date TEXT, time TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS admin (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL)")
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS teachers (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, username TEXT UNIQUE NOT NULL,
        branch TEXT, teacher_uid TEXT UNIQUE, email TEXT UNIQUE NOT NULL, mobile TEXT NOT NULL, subject TEXT,
        class_time TEXT, end_time TEXT, password TEXT NOT NULL, status TEXT DEFAULT 'Active', face_data TEXT, raw_password TEXT
    )''')
    
    try:
        cursor.execute("ALTER TABLE teachers ADD COLUMN raw_password TEXT")
        conn.commit()
    except:
        pass

    cursor.execute('''CREATE TABLE IF NOT EXISTS teacher_attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT, teacher_id INTEGER, date TEXT NOT NULL, 
        time TEXT NOT NULL, status TEXT NOT NULL, location TEXT, FOREIGN KEY(teacher_id) REFERENCES teachers(id)
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS deletion_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, teacher_id INTEGER, branch TEXT,
        student_name TEXT, student_roll TEXT, student_id_short TEXT, reason TEXT,
        status TEXT DEFAULT 'Pending', request_time TEXT, resolve_time TEXT
    )''')

    cursor.execute("SELECT * FROM admin WHERE username='admin'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO admin (username, password) VALUES (?, ?)", ('admin', generate_password_hash('admin123')))

    conn.commit()
    conn.close()

init_db()

def get_db_connection():
    conn = sqlite3.connect('attendance.db')
    conn.row_factory = sqlite3.Row
    return conn 

@app.route('/send-otp', methods=['POST'])
def send_otp():
    import random
    email = request.form.get('email', '').strip().lower()
    if not email: return {"status": "error"}
    otp = str(random.randint(100000, 999999))
    otp_store[email] = {"otp": otp, "expiry": datetime.now() + timedelta(minutes=5)}
    return {"status": "success", "otp": otp}

@app.route('/verify-register-otp', methods=['POST'])
def verify_register_otp():
    email = request.form.get('email', '').strip().lower()
    user_otp = request.form.get('otp')
    if email in otp_store and otp_store[email]["otp"] == user_otp:
        if datetime.now() < otp_store[email]["expiry"]: return {"status": "success"}
    return {"status": "error", "message": "Invalid or Expired OTP."}

# 🔥 INTRO SCREEN ROUTE 🔥
@app.route('/intro')
def intro_screen():
    # 🔥 Instead of showing intro.html, go to hacking verification screen
    return redirect(url_for('verifying'))

@app.route('/verifying')
def verifying():
    next_url = session.get("next_url", "/")
    return render_template("verifying.html", next_url=next_url)

@app.route("/", methods=["GET","POST"])
def home():
    if request.method == "GET":
        session.clear() 
        return render_template("login.html")

    if request.method == "POST":
        raw_username = request.form.get("username", "").strip()
        username = raw_username.lower()
        password = request.form.get("password", "")

        # 1. PRINCIPAL LOGIN
        if raw_username == "PRINCIPAL" and password == "GDGPH":
            session.clear() 
            session["user"] = "principal"
            session["next_url"] = "/principal/dashboard"
            return redirect("/intro") # Intro -> Dashboard

        # 2. ADMIN LOGIN
        if (username == "admin" or username == "student" or username == "") and password == "54321":
            session.clear() 
            session["user"] = "admin" 
            session["next_url"] = "/dashboard"
            return redirect("/intro") # Intro -> Dashboard
            
        # 3. TEACHER LOGIN
        conn = get_db_connection()
        teacher = conn.execute('SELECT * FROM teachers WHERE email = ? OR username = ?', (username, username)).fetchone()
        conn.close()

        if teacher:
            password_match = False
            if teacher['password'] == password: password_match = True
            else:
                try:
                    if check_password_hash(teacher['password'], password): password_match = True
                except: pass

            if password_match:
                if teacher['status'] == 'Pending':
                    return render_template("login.html", error="Account is Pending Approval from Principal.")
                elif teacher['status'] != 'Active': 
                    return render_template("login.html", error="Account Inactive. Contact Admin.")
                
                session.clear() 
                session['teacher_id'] = teacher['id']
                session['teacher_name'] = teacher['name']
                session["next_url"] = "/teacher/dashboard"
                return redirect("/intro") # Intro -> Dashboard
                
        return render_template("login.html", error="Wrong Username or Password")

@app.route('/teacher/login', methods=['GET', 'POST'])
def teacher_login():
    if request.method == 'GET':
        session.clear() 
        return render_template('teacher_login.html')

    if request.method == 'POST':
        email_or_id = request.form.get('email', '').strip().lower() 
        password = request.form.get('password', '')
        conn = get_db_connection()
        teacher = conn.execute('SELECT * FROM teachers WHERE email = ? OR username = ?', (email_or_id, email_or_id)).fetchone()
        conn.close()

        if teacher:
            password_match = False
            if teacher['password'] == password:
                password_match = True
            else:
                try:
                    if check_password_hash(teacher['password'], password):
                        password_match = True
                except:
                    pass

            if password_match:
                if teacher['status'] == 'Pending':
                    flash('Account is Pending Approval from Principal.', 'error')
                elif teacher['status'] != 'Active':
                    flash('Account is Inactive or Suspended. Contact Admin.', 'error')
                else:
                    session.clear() 
                    session['teacher_id'] = teacher['id']
                    session['teacher_name'] = teacher['name']
                    session["next_url"] = "/teacher/dashboard"
                    return redirect("/intro") # Intro -> Dashboard
            else:
                flash('Wrong Username or Password', 'error')
        else:
            flash('Wrong Username or Password', 'error')
            
    return render_template('teacher_login.html')

@app.route('/principal/dashboard')
def principal_dashboard():
    if session.get("user") != "principal": return redirect("/")
    conn = get_db_connection()
    pending_teachers = conn.execute("SELECT * FROM teachers WHERE status='Pending'").fetchall()
    active_teachers = conn.execute("SELECT id, name, teacher_uid, mobile, subject, branch FROM teachers WHERE status='Active'").fetchall()
    del_reqs = conn.execute("SELECT * FROM deletion_requests WHERE status='Pending'").fetchall()
    conn.close()
    return render_template('principal_dashboard.html', teachers=active_teachers, pending_teachers=pending_teachers, requests=del_reqs)

@app.route('/principal/accept_new_teacher', methods=['POST'])
def principal_accept_new_teacher():
    if session.get("user") != "principal": return jsonify({"status": "error"})
    teacher_id = request.form.get('id')
    conn = get_db_connection()
    conn.execute("UPDATE teachers SET status='Active' WHERE id=?", (teacher_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route('/principal/decline_new_teacher', methods=['POST'])
def principal_decline_new_teacher():
    if session.get("user") != "principal": return jsonify({"status": "error"})
    teacher_id = request.form.get('id')
    conn = get_db_connection()
    conn.execute("DELETE FROM teachers WHERE id=?", (teacher_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route('/principal/accept_delete/<int:req_id>', methods=['POST'])
def principal_accept_delete(req_id):
    if session.get("user") != "principal": return jsonify({"status": "error"})
    conn = get_db_connection()
    req = conn.execute("SELECT * FROM deletion_requests WHERE id=?", (req_id,)).fetchone()
    if req:
        student_name = req['student_name']
        student_id_short = req['student_id_short']
        student_roll = req['student_roll']
        conn.execute("DELETE FROM students WHERE name=? AND (roll=? OR roll=?)", (student_name, student_id_short, student_roll))
        conn.execute("DELETE FROM attendance WHERE name=?", (student_name,))
        deleted_anything = False
        for folder in glob.glob(f"static/dataset/{student_name}_*"):
            if os.path.exists(folder):
                shutil.rmtree(folder)
                deleted_anything = True
        if deleted_anything:
            os.system("python train.py")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("UPDATE deletion_requests SET status='Approved', resolve_time=? WHERE id=?", (now_str, req_id))
        conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route('/principal/fire_teacher/<int:teacher_id>', methods=['POST'])
def principal_fire_teacher(teacher_id):
    if session.get("user") != "principal": return jsonify({"status": "error"})
    conn = get_db_connection()
    conn.execute("DELETE FROM teacher_attendance WHERE teacher_id=?", (teacher_id,))
    conn.execute("DELETE FROM deletion_requests WHERE teacher_id=?", (teacher_id,))
    conn.execute("DELETE FROM teachers WHERE id=?", (teacher_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route('/teacher/dashboard')
def teacher_dashboard():
    if not session.get('teacher_id'): return redirect(url_for('home'))
    conn = get_db_connection()
    teacher = conn.execute('SELECT * FROM teachers WHERE id = ?', (session['teacher_id'],)).fetchone()
    total_students = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    one_month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    history = conn.execute('SELECT date, time, status, location FROM teacher_attendance WHERE teacher_id = ? AND date >= ? ORDER BY date DESC', (session['teacher_id'], one_month_ago)).fetchall()
    cycle_msg, cycle_error = None, False
    first_record_row = conn.execute('SELECT MIN(date) FROM attendance').fetchone()
    if first_record_row and first_record_row[0]:
        days_passed = (datetime.now() - datetime.strptime(first_record_row[0], "%Y-%m-%d")).days
        if days_passed > 32: cycle_msg, cycle_error = "🛑 MISTAKE: 32-day deadline passed! Data is locked.", True
        elif days_passed > 30: cycle_msg = f"⚠️ WARNING: 30 days complete. Export data within {32 - days_passed} days!"
    conn.close()
    return render_template('teacher_dashboard.html', teacher=teacher, total_students=total_students, history=history, cycle_msg=cycle_msg, cycle_error=cycle_error)

@app.route('/teacher/student_list')
def teacher_student_list():
    if not session.get('teacher_id'): return redirect("/")
    conn = get_db_connection()
    today = datetime.now().strftime("%Y-%m-%d")
    students = conn.execute('''
        SELECT s.name, s.roll, a.time, a.date, a.subject
        FROM students s LEFT JOIN attendance a ON s.name = a.name AND a.date = ?
    ''', (today,)).fetchall()
    student_data = [{'name': s['name'], 'roll': s['roll'], 'subject': s['subject'] if s['subject'] else '--', 'status': 'Present' if s['time'] else 'Absent', 'time': s['time'] if s['time'] else '--:--', 'date': today if s['time'] else '--'} for s in students]
    conn.close()
    return render_template('teacher_student_list.html', students=student_data, total_students=len(student_data))

@app.route("/start_new_month")
def start_new_month():
    if not session.get('teacher_id'): return redirect("/")
    conn = get_db_connection()
    conn.execute("DELETE FROM attendance")
    conn.execute("DELETE FROM teacher_attendance")
    conn.commit()
    conn.close()
    flash("New month started! All records cleared successfully. 🧹", "success")
    return redirect(url_for('teacher_dashboard'))

@app.route("/export_student_attendance")
def export_student_attendance():
    if not session.get('teacher_id'): return redirect("/")
    conn = get_db_connection()
    rows = conn.execute("SELECT name, date, time FROM attendance").fetchall()
    conn.close()
    filename = "Student_Attendance_Monthly.csv"
    with open(filename, "w") as f:
        f.write("Name,Date,Time,Status\n")
        for r in rows: f.write(f"{r['name']},{r['date']},{r['time']},Present\n")
    return send_file(filename, as_attachment=True)

@app.route("/verify_attendance_rules", methods=['POST'])
def verify_attendance_rules():
    if not session.get('teacher_id'): return jsonify({"status": "error", "message": "Session Expired"})
    lat, lon = float(request.form.get('lat', 0)), float(request.form.get('lon', 0))
    dist = calculate_distance(lat, lon, COLLEGE_LAT, COLLEGE_LON)
    date_str, time_str = datetime.now().strftime("%Y-%m-%d"), datetime.now().strftime("%H:%M:%S")
    status = 'Present' if dist <= ALLOWED_RADIUS_KM else 'Absent (Far Location)'
    conn = get_db_connection()
    conn.execute('INSERT INTO teacher_attendance (teacher_id, date, time, status, location) VALUES (?, ?, ?, ?, ?)', (session['teacher_id'], date_str, time_str, status, f"{round(lat,4)}, {round(lon,4)}"))
    conn.commit()
    conn.close()
    return jsonify({"status": "success" if dist <= ALLOWED_RADIUS_KM else "warning", "dist": round(dist, 2)})

@app.route("/export_teacher_attendance")
def export_teacher_attendance():
    if not session.get('teacher_id'): return redirect("/")
    conn = get_db_connection()
    rows = conn.execute('''
        SELECT t.name, t.teacher_uid, t.subject, t.class_time, t.end_time, ta.date, ta.status
        FROM teacher_attendance ta JOIN teachers t ON ta.teacher_id = t.id WHERE ta.teacher_id = ? ORDER BY ta.date DESC
    ''', (session['teacher_id'],)).fetchall()
    conn.close()
    filename = f"Attendance_Report_{session['teacher_name']}.csv"
    with open(filename, "w") as f:
        f.write("NAME,TCH ID,SUBJECT,CLASS START,CLASS END,DATE,STATUS\n")
        for r in rows: f.write(f"{r['name']},{r['teacher_uid']},{r['subject']},{r['class_time']},{r['end_time']},{r['date']},{r['status']}\n")
    return send_file(filename, as_attachment=True)

@app.route('/teacher/profile')
def teacher_profile():
    if not session.get('teacher_id'): return redirect(url_for('home'))
    conn = get_db_connection()
    teacher = conn.execute('SELECT * FROM teachers WHERE id = ?', (session['teacher_id'],)).fetchone()
    two_hours_ago = (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    del_requests = conn.execute('''
        SELECT * FROM deletion_requests 
        WHERE teacher_id = ? AND (status = 'Pending' OR (status = 'Approved' AND resolve_time >= ?)) ORDER BY id DESC
    ''', (session['teacher_id'], two_hours_ago)).fetchall()
    conn.close()
    return render_template('teacher_profile.html', teacher=teacher, requests=del_requests, date=datetime.now().strftime("%d %b %Y"))

@app.route('/teacher/request_deletion', methods=['POST'])
def request_deletion():
    if not session.get('teacher_id'): return redirect(url_for('home'))
    name, roll, sid, reason = request.form.get('student_name'), request.form.get('student_roll'), request.form.get('student_id'), request.form.get('reason')
    conn = get_db_connection()
    teacher = conn.execute("SELECT branch FROM teachers WHERE id=?", (session['teacher_id'],)).fetchone()
    conn.execute('''INSERT INTO deletion_requests (teacher_id, branch, student_name, student_roll, student_id_short, reason, request_time) 
        VALUES (?, ?, ?, ?, ?, ?, ?)''', (session['teacher_id'], teacher['branch'], name, roll, sid, reason, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    flash("Deletion Request Sent to Principal!", "success")
    return redirect(url_for('teacher_profile'))

@app.route('/teacher/edit_profile', methods=['POST'])
def teacher_edit_profile():
    if not session.get('teacher_id'): return redirect(url_for('home'))
    conn = get_db_connection()
    data = (request.form.get('name'), request.form.get('username').strip().lower(), request.form.get('mobile'), request.form.get('email').strip().lower(), request.form.get('subject'), request.form.get('class_time'), request.form.get('end_time'), session['teacher_id'])
    try:
        conn.execute('''UPDATE teachers SET name=?, username=?, mobile=?, email=?, subject=?, class_time=?, end_time=? WHERE id=?''', data)
        conn.commit()
        flash("Profile Updated Successfully! ✅", "success")
    except: flash("❌ Username or Email taken!", "error")
    finally: conn.close()
    return redirect(url_for('teacher_profile'))

@app.route('/teacher/settings', methods=['GET', 'POST'])
def teacher_settings():
    if not session.get('teacher_id'): return redirect(url_for('home'))
    conn = get_db_connection()
    teacher = conn.execute('SELECT * FROM teachers WHERE id = ?', (session['teacher_id'],)).fetchone()
    if request.method == 'POST':
        if check_password_hash(teacher['password'], request.form.get('current_password')):
            if request.form.get('new_password') == request.form.get('confirm_password'):
                conn.execute('UPDATE teachers SET password=? WHERE id=?', (generate_password_hash(request.form.get('new_password')), session['teacher_id']))
                conn.commit()
                flash("✅ Password updated!", "success")
            else: flash("❌ New passwords do not match!", "error")
        else: flash("❌ Current password wrong!", "error")
    conn.close()
    return render_template('teacher_settings.html', teacher=teacher)

@app.route('/teacher/update_class', methods=['POST'])
def update_class():
    if not session.get('teacher_id'): return redirect("/")
    conn = get_db_connection()
    conn.execute('UPDATE teachers SET class_time = ? WHERE id = ?', (request.form.get('new_time'), session['teacher_id']))
    conn.commit()
    conn.close()
    flash("Class Time Updated Successfully! ✅", "success")
    return redirect(url_for('teacher_dashboard'))

@app.route('/terms_conditions')
def terms_conditions():
    return render_template('terms_conditions.html')

@app.route('/teacher/register', methods=['GET', 'POST'])
def teacher_register():
    if request.method == 'POST':
        name, username = request.form.get('name'), request.form.get('username', '').strip().lower()
        branch, email = request.form.get('branch'), request.form.get('email', '').strip().lower()
        mobile, password = request.form.get('mobile'), request.form.get('password')
        teacher_uid = f"TCH-{mobile[:2]}{mobile[-2:]}" if len(mobile) >= 4 else f"TCH-{mobile}"
        
        if email not in otp_store or otp_store[email]["otp"] != request.form.get('otp'):
            flash("Invalid or Expired OTP. Please verify again!", "error")
            return redirect(url_for('teacher_register'))
            
        if password != request.form.get('confirm_password'):
            flash("Passwords do not match!", "error")
            return redirect(url_for('teacher_register'))

        status = 'Active' if email == 'vatsnagwan8586@gmail.com' else 'Pending'

        conn = get_db_connection()
        try:
            if email == 'vatsnagwan8586@gmail.com':
                teacher_to_clear = conn.execute("SELECT id FROM teachers WHERE email = ?", (email,)).fetchone()
                if teacher_to_clear:
                    t_id = teacher_to_clear['id']
                    conn.execute("DELETE FROM teacher_attendance WHERE teacher_id = ?", (t_id,))
                    conn.execute("DELETE FROM deletion_requests WHERE teacher_id = ?", (t_id,))
                    conn.execute("DELETE FROM teachers WHERE id = ?", (t_id,))
                    conn.commit()

            conn.execute('''INSERT INTO teachers (name, username, branch, teacher_uid, email, mobile, subject, class_time, end_time, password, status, raw_password) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                         (name, username, branch, teacher_uid, email, mobile, request.form.get('subject'), request.form.get('class_time'), request.form.get('end_time'), generate_password_hash(password), status, password))
            conn.commit()
            if email in otp_store: del otp_store[email]
            
            session['registered_alert'] = True 
            return redirect(url_for('terms_conditions')) 
            
        except sqlite3.Error as e:
            flash(f'Registration failed! (Username/Email might already exist)', "error")
        finally: 
            conn.close()
    return render_template('teacher_register.html')

@app.route("/dashboard")
def dashboard():
    if "user" not in session: return redirect("/")
    conn = sqlite3.connect("attendance.db")
    total = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    names = [r[0] for r in conn.execute("SELECT name FROM students").fetchall()]
    conn.close()
    return render_template("dashboard.html", total_students=total, student_list=names)

# ==========================================================
# 🔥 DEVELOPER LOCK ADDED (FOR RENDER/PUBLIC DEPLOYMENT) 🔥
# ==========================================================
@app.route("/capture_images")
def capture_images():
    # Render ya kisi aur cloud par camera block karne ka logic
    if 'localhost' not in request.host and '127.0.0.1' not in request.host:
        flash("⚠️ Developer Restricted: Camera works only on Localhost!", "error")
        return redirect("/dashboard")

    name = request.args.get("name")
    full_roll = request.args.get("roll")
    
    if not name or not full_roll: 
        return redirect("/dashboard")
    
    student_id = f"{full_roll[0]}{full_roll[-3:]}" if len(full_roll) >= 4 else full_roll
        
    conn = sqlite3.connect("attendance.db")
    conn.execute("INSERT INTO students (name, roll) VALUES (?, ?)", (name, student_id))
    conn.commit()
    conn.close()
    
    folder = f"static/dataset/{name}_{student_id}"
    os.makedirs(folder, exist_ok=True)
    
    faceCascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    cam = cv2.VideoCapture(0)
    time.sleep(1)
    
    count = 0
    while count < 20:
        ret, frame = cam.read()
        if ret:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = faceCascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(50, 50))
            
            display_frame = frame.copy()
            for (x, y, w, h) in faces:
                cv2.rectangle(display_frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                cv2.putText(display_frame, f"Face Detected: {count}/20", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            
            cv2.imshow(f"Capturing Face: {name} (ID: {student_id})", display_frame)
            
            if len(faces) > 0:
                cv2.imwrite(f"{folder}/{count}.jpg", frame)
                count += 1
                time.sleep(0.2)
            
        if cv2.waitKey(100) & 0xFF == ord('q'):
            break
            
    cam.release()
    cv2.destroyAllWindows()
    
    os.system("python train.py")
    return redirect("/dashboard")

@app.route("/remove_student", methods=["POST"])
def remove_student():
    name = request.form.get("name")
    conn = sqlite3.connect("attendance.db")
    conn.execute("DELETE FROM students WHERE name=?", (name,))
    conn.commit()
    conn.close()
    return redirect("/dashboard")

@app.route("/recognize")
def recognize():
    # 🔥 YAHAN BHI LAGA HAI DEVELOPER LOCK 🔥
    if 'localhost' not in request.host and '127.0.0.1' not in request.host:
        flash("⚠️ Developer Restricted: Camera access is disabled on public server!", "error")
        return redirect("/dashboard")

    name = request.args.get("name", "").strip()
    roll = request.args.get("roll", "").strip()
    subject = request.args.get("class", "").strip()
    
    if not name or not roll or not subject:
        flash("FIRST FILL ALL INFORMATION", "error")
        return redirect("/dashboard")
        
    if not os.path.exists('trainer.yml'):
        flash("MODEL NOT FOUND! Please 'Add Student' first.", "error")
        return redirect("/dashboard")
        
    result = subprocess.run(["python", "face_recognize.py", name, roll, subject], capture_output=True, text=True)
    output = result.stdout.strip()
    
    if "MISMATCH" in output:
        flash("❌ THIS STUDENT FACE IS MISMATCH!", "error")
    elif "SUCCESS" in output:
        flash(f"✅ Attendance Marked for {name}!", "success")
    else:
        flash("⚠️ Camera closed or face not clear.", "warning")
        
    return redirect("/dashboard")

@app.route("/attendance")
def attendance():
    if "user" not in session: return redirect("/")
    conn = get_db_connection()
    data = conn.execute("SELECT name, roll, subject, date, time FROM attendance ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("attendance.html", data=data)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)