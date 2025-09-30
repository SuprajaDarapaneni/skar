from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file , make_response
import mysql.connector
import datetime
import os
from werkzeug.utils import secure_filename
from io import BytesIO
from flask import make_response, render_template_string
from xhtml2pdf import pisa
import json
import pandas as pd




app = Flask(__name__)
app.secret_key = "supersecretkey"

# ------------------- FILE UPLOAD CONFIG -------------------
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ------------------- MYSQL CONNECTION HELPER -------------------
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="hr_db"
    )

# ------------------- AUTH -------------------
@app.route('/')
def home():
    return render_template('main.html')

@app.route('/signinpage')
def signinpage():
    return render_template('signin.html')

@app.route('/signin', methods=['POST'])
def signin():
    email = request.form['email']
    password = request.form['password']

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email, role FROM users WHERE email=%s AND password=%s",
                   (email, password))
    user = cursor.fetchone()

    if not user:
        conn.close()
        return "Invalid email or password"

    session['user'] = {'id': user[0], 'name': user[1], 'email': user[2], 'role': user[3]}

    # ---------------- CLOCK IN ----------------
    now = datetime.datetime.now()
    today = now.date()

    cursor.execute("SELECT id FROM work_logs WHERE user_id=%s AND log_date=%s", (user[0], today))
    existing = cursor.fetchone()
    if not existing:
        cursor.execute("INSERT INTO work_logs (user_id, log_date, clock_in) VALUES (%s, %s, %s)",
                       (user[0], today, now))
        conn.commit()
    # -----------------------------------------

    conn.close()

    role_redirect = {
        'manager': 'manager',
        'employee': 'employee',
        'hr': 'hr',
        'admin': 'admin'
    }
    return redirect(url_for(role_redirect.get(user[3].lower(), 'home')))

@app.route('/logout')
def logout():
    if 'user' in session:
        user_id = session['user']['id']
        now = datetime.datetime.now()
        today = now.date()

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE work_logs SET clock_out=%s WHERE user_id=%s AND log_date=%s",
                       (now, user_id, today))
        conn.commit()
        cursor.close()
        conn.close()

    session.clear()
    return redirect(url_for('signinpage'))



# ------------------- PAGES -------------------
@app.route('/employee')
def employee():
    if 'user' not in session:
        return redirect(url_for('signinpage'))
    if session['user']['role'].lower() != 'employee':
        return "Unauthorized", 403
    return render_template('employee.html', user=session['user'])

@app.route('/manager')
def manager():
    if 'user' not in session:
        return redirect(url_for('signinpage'))
    return render_template('manager.html', user=session['user'])

@app.route('/hr')
def hr():
    if 'user' not in session:
        return redirect(url_for('signinpage'))
    return render_template('hr.html', user=session['user'])

@app.route('/admin')
def admin():
    if 'user' not in session:
        return redirect(url_for('signinpage'))
    return render_template('admin.html', user=session['user'])

# ------------------- EMPLOYEE ATTENDANCE -------------------
@app.route('/mark_attendance', methods=['POST'])
def mark_attendance():
    if 'user' not in session:
        return "Not logged in", 401

    user_id = session['user']['id']
    today = datetime.date.today()
    if today.weekday() == 6:  # Sunday
        return jsonify({"message": "Today is a holiday (Sunday)."}), 400

    status = request.json.get('status')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM attendance WHERE user_id=%s AND date=%s", (user_id, today))
    already = cursor.fetchone()
    if already:
        conn.close()
        return jsonify({"message": "Attendance already marked for today."})

    cursor.execute("INSERT INTO attendance (user_id, date, status) VALUES (%s, %s, %s)",
                   (user_id, today, status))
    conn.commit()
    conn.close()
    return jsonify({"message": "Attendance marked successfully."})

@app.route('/attendance_summary')
def attendance_summary():
    if 'user' not in session:
        return "Not logged in", 401

    user_id = session['user']['id']
    today = datetime.date.today()
    first_day = today.replace(day=1)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT status, COUNT(*) as count
        FROM attendance
        WHERE user_id=%s AND date BETWEEN %s AND %s
        GROUP BY status
    """, (user_id, first_day, today))
    rows = cursor.fetchall()
    conn.close()

    summary = {"Present": 0, "Absent": 0, "Leave": 0}
    for r in rows:
        summary[r['status']] = r['count']

    return jsonify(summary)

# ------------------- USER DATA -------------------
@app.route('/api/users')
def api_users():
    if 'user' not in session:
        return jsonify({"message": "Not logged in"}), 401

    current_user = session['user']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if current_user['role'].lower() in ['admin', 'hr', 'manager']:
        cursor.execute("""
            SELECT id, name, email, role, phone, country, image, status
            FROM users
            WHERE role != 'admin'
        """)
    else:
        cursor.execute("""
            SELECT id, name, email, role, phone, country, image, status
            FROM users
            WHERE id=%s
        """, (current_user['id'],))
    users = cursor.fetchall()
    cursor.close()
    conn.close()

    for u in users:
        if u['image']:
            u['image'] = url_for('static', filename=f'uploads/{u["image"]}')
        else:
            u['image'] = url_for('static', filename='images/default.png')
    return jsonify(users)

@app.route('/api/update_user/<int:id>', methods=['POST'])
def update_user(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    name = request.form['name']
    email = request.form['email']
    role = request.form['role']

    # ---------------- Profile Picture ----------------
    profile_pic = request.files.get('profile_pic')
    pic_filename = None
    if profile_pic and profile_pic.filename != "":
        pic_filename = secure_filename(profile_pic.filename)
        upload_folder = app.config.get('UPLOAD_FOLDER', 'static/uploads')
        os.makedirs(upload_folder, exist_ok=True)
        profile_pic.save(os.path.join(upload_folder, pic_filename))
        pic_path = f'{pic_filename}'  # DB lo matrame filename store cheyali
    else:
        pic_path = None

    # ---------------- Documents ----------------
    documents_files = request.files.getlist('documents')
    documents_paths = []
    upload_folder = app.config.get('UPLOAD_FOLDER', 'static/uploads')
    os.makedirs(upload_folder, exist_ok=True)

    for doc in documents_files:
        if doc and doc.filename != "":
            doc_filename = secure_filename(doc.filename)
            doc.save(os.path.join(upload_folder, doc_filename))
            documents_paths.append(doc_filename)  # DB lo filename matrame

    # Fetch existing documents from DB
    cursor.execute("SELECT documents FROM users WHERE id=%s", (id,))
    existing = cursor.fetchone()
    existing_docs = []
    if existing and existing['documents']:
        try:
            existing_docs = json.loads(existing['documents'])
        except:
            existing_docs = []

    # Merge old + new
    all_docs = existing_docs + documents_paths

    # ---------------- Update DB ----------------
    if pic_path:  # only update image if new file uploaded
        cursor.execute("""
            UPDATE users 
            SET name=%s, email=%s, role=%s, image=%s, documents=%s 
            WHERE id=%s
        """, (name, email, role, pic_path, json.dumps(all_docs), id))
    else:
        cursor.execute("""
            UPDATE users 
            SET name=%s, email=%s, role=%s, documents=%s 
            WHERE id=%s
        """, (name, email, role, json.dumps(all_docs), id))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Profile updated successfully"})


# ------------------- ADD NEW EMPLOYEE -------------------

@app.route('/add_employee', methods=['POST'])
def add_employee():
    if 'user' not in session:
        return jsonify({"message": "Not logged in"}), 401
    if session['user']['role'].lower() not in ['admin', 'hr', 'manager']:
        return jsonify({"message": "Permission denied"}), 403

    # --- Get form values ---
    name = request.form.get('name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    country = request.form.get('country')
    role = request.form.get('role')
    status = request.form.get('status')
    password = request.form.get('password')   # 👈 new field
    join_date = datetime.date.today()
    image_file = request.files.get('image')

    # --- Handle image ---
    img_filename = None
    if image_file and allowed_file(image_file.filename):
        img_filename = secure_filename(image_file.filename)
        image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], img_filename))

    # --- Insert into DB ---
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO users (name, email, phone, country, role, status, join_date, image, password)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (name, email, phone, country, role, status, join_date, img_filename, password))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Employee added successfully"})


# ------------------- LEAVE REQUEST SYSTEM -------------------
@app.route('/apply_leave', methods=['POST'])
def apply_leave():
    if 'user' not in session:
        return jsonify({"message":"Not logged in"}), 401
    user_id = session['user']['id']
    date = request.json.get('date')
    reason = request.json.get('reason')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO leave_requests (user_id, date, reason)
        VALUES (%s, %s, %s)
    """, (user_id, date, reason))
    conn.commit()
    conn.close()
    return jsonify({"message":"Leave request submitted"})

@app.route('/api/leave_requests')
def get_leave_requests():
    if 'user' not in session or session['user']['role'].lower() != 'admin':
        return jsonify({"message":"Unauthorized"}), 403
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT lr.id, u.name, lr.date, lr.reason, lr.status
        FROM leave_requests lr
        JOIN users u ON lr.user_id=u.id
        ORDER BY lr.created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return jsonify(rows)

@app.route('/api/leave_requests/<int:req_id>', methods=['POST'])
def handle_leave_request(req_id):
    if 'user' not in session or session['user']['role'].lower() != 'admin':
        return jsonify({"message": "Unauthorized"}), 403

    action = request.json.get('action')  # approve/reject
    if not action or action not in ['approve', 'reject']:
        return jsonify({"message": "Invalid action"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT user_id, date FROM leave_requests WHERE id=%s", (req_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({"message": "Leave request not found"}), 404

    user_id, leave_date = row
    if action == 'approve':
        date_obj = leave_date if isinstance(leave_date, datetime.date) else datetime.datetime.strptime(str(leave_date), "%Y-%m-%d").date()
        cursor.execute(
            "INSERT INTO attendance (user_id, date, status) VALUES (%s, %s, 'Leave')",
            (user_id, date_obj)
        )
        cursor.execute("UPDATE leave_requests SET status='approved', approved_date=CURDATE() WHERE id=%s", (req_id,))
    elif action == 'reject':
        cursor.execute("UPDATE leave_requests SET status='rejected' WHERE id=%s", (req_id,))

    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": f"Leave {action}d"})

#-------- EMPLOYEES API
@app.route("/api/employees")
def get_employees():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users")
    employees = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(employees)

# ------------------- ADMIN OVERVIEW -------------------
@app.route('/api/overview_data')
def overview_data():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Total employees excluding admin
    cursor.execute("SELECT COUNT(*) AS total_employees FROM users WHERE role!='admin'")
    total_employees = cursor.fetchone()['total_employees']

    # Present today
    cursor.execute("SELECT COUNT(*) AS present_today FROM attendance WHERE date=CURDATE() AND status='Present'")
    present_today = cursor.fetchone()['present_today']

    # On leave today
    cursor.execute("SELECT COUNT(*) AS on_leave FROM attendance WHERE date=CURDATE() AND status='Leave'")
    on_leave = cursor.fetchone()['on_leave']

    # Departments count
    cursor.execute("SELECT COUNT(*) AS departments FROM departments")
    departments = cursor.fetchone()['departments']

    conn.close()
    return jsonify({
        "total_employees": total_employees,
        "present_today": present_today,
        "on_leave": on_leave,
        "departments": departments
    })

@app.route('/api/attendance/<int:user_id>')
def get_employee_attendance(user_id):
    if 'user' not in session or session['user']['role'].lower() != 'admin':
        return jsonify({"message": "Unauthorized"}), 403

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT date, status
        FROM attendance
        WHERE user_id=%s
        ORDER BY date ASC
    """, (user_id,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(rows)

# ------------------- DELETE EMPLOYEE -------------------
@app.route('/api/delete_user/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    if 'user' not in session:
        return jsonify({"message": "Not logged in"}), 401
    if session['user']['role'].lower() not in ['admin', 'hr', 'manager']:
        return jsonify({"message": "Permission denied"}), 403

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM attendance WHERE user_id=%s", (user_id,))
    cursor.execute("DELETE FROM leave_requests WHERE user_id=%s", (user_id,))
    cursor.execute("DELETE FROM users WHERE id=%s", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Employee deleted successfully"})

@app.route("/api/users/<int:id>")
def get_user(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE id=%s", (id,))
    user = cursor.fetchone()
    conn.close()
    return jsonify(user)

@app.route('/api/my_approved_leaves')
def my_approved_leaves():
    if 'user' not in session:
        return jsonify({"message": "Not logged in"}), 401
    
    user_id = session['user']['id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT date, approved_date
        FROM leave_requests
        WHERE user_id=%s AND status='approved'
        ORDER BY approved_date DESC
    """, (user_id,))
    leaves = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(leaves)

@app.route("/admin/attendance_report")
def attendance_report():
    report_type = request.args.get("type", "daily")
    mydb = get_db_connection()
    cursor = mydb.cursor(dictionary=True)

    if report_type == "daily":
        cursor.execute("""
            SELECT status, COUNT(*) as count 
            FROM attendance 
            WHERE DATE(date) = CURDATE()
            GROUP BY status
        """)
    elif report_type == "weekly":
        cursor.execute("""
            SELECT status, COUNT(*) as count 
            FROM attendance 
            WHERE YEARWEEK(date) = YEARWEEK(CURDATE())
            GROUP BY status
        """)
    elif report_type == "monthly":
        cursor.execute("""
            SELECT status, COUNT(*) as count 
            FROM attendance 
            WHERE MONTH(date) = MONTH(CURDATE()) 
              AND YEAR(date) = YEAR(CURDATE())
            GROUP BY status
        """)

    data = cursor.fetchall()
    cursor.close()
    mydb.close()

    summary = {"Present": 0, "Absent": 0, "Leave": 0}
    for row in data:
        summary[row["status"]] = row["count"]

    return jsonify(summary)
@app.route('/api/payroll', methods=['GET', 'POST'])
def api_payroll():
    if 'user' not in session:
        return jsonify({"message": "Not logged in"}), 401
    if session['user']['role'].lower() not in ['admin', 'hr']:
        return jsonify({"message": "Permission denied"}), 403

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'GET':
        cursor.execute("""
            SELECT 
                p.id, 
                u.name AS employee_name,   -- 👈 employee name
                p.month, 
                p.basic, 
                p.bonus, 
                p.total,
                COALESCE(p.status, 'pending') AS status   -- 👈 default if null
            FROM payroll p
            JOIN users u ON p.user_id = u.id
            ORDER BY p.month DESC
        """)
        payrolls = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(payrolls)

    elif request.method == 'POST':
        data = request.get_json()
        user_id = data.get('user_id')
        month = data.get('month')
        basic = float(data.get('basic', 0))
        bonus = float(data.get('bonus', 0))
        total = basic + bonus
        if month and len(month) == 7:   # 'YYYY-MM'
             month = month + "-05" 
        cursor.execute("""
            INSERT INTO payroll (user_id, month, basic, bonus, total)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, month, basic, bonus, total))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": "Payroll added successfully"})


@app.route('/api/payroll/<int:payroll_id>', methods=['DELETE'])
def delete_payroll(payroll_id):
    if 'user' not in session:
        return jsonify({"message": "Not logged in"}), 401
    if session['user']['role'].lower() not in ['admin', 'hr']:
        return jsonify({"message": "Permission denied"}), 403

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM payroll WHERE id=%s", (payroll_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Payroll deleted successfully"})

# ------------------- EMPLOYEE OWN PAYROLL -------------------
@app.route('/api/my_payroll')
def my_payroll():
    if 'user' not in session:
        return jsonify({"message": "Not logged in"}), 401
    if session['user']['role'].lower() != 'employee':
        return jsonify({"message": "Permission denied"}), 403

    user_id = session['user']['id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
         SELECT id, month, basic, bonus, total, COALESCE(status,'pending') AS status 
         FROM payroll
         WHERE user_id=%s
         ORDER BY month DESC
    """, (user_id,))
    payrolls = cursor.fetchall()
    cursor.close()
    conn.close()

    return jsonify(payrolls)

@app.route('/api/payroll_status/<int:payroll_id>', methods=['POST'])
def update_payroll_status(payroll_id):
    if 'user' not in session:
        return jsonify({"message": "Not logged in"}), 401
    if session['user']['role'].lower() not in ['admin', 'hr']:
        return jsonify({"message": "Permission denied"}), 403

    data = request.get_json()
    status = data.get('status')  # e.g., 'paid'
    if not status:
        return jsonify({"message": "Status required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE payroll SET status=%s WHERE id=%s", (status, payroll_id))
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": f"Payroll marked as {status}"})
@app.route('/api/chat_users')
def chat_users():
    if 'user' not in session:
        return jsonify({"message":"Not logged in"}), 401

    current_user_id = session['user']['id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name FROM users WHERE id != %s", (current_user_id,))
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(users)

@app.route('/api/chat_messages/<int:receiver_id>')
def chat_messages(receiver_id):
    if 'user' not in session:
        return jsonify({"message":"Not logged in"}), 401

    sender_id = session['user']['id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT m.id, m.sender_id, m.receiver_id, m.message, m.timestamp, u.name as sender_name
        FROM messages m
        JOIN users u ON m.sender_id = u.id
        WHERE (sender_id=%s AND receiver_id=%s)
           OR (sender_id=%s AND receiver_id=%s)
        ORDER BY m.timestamp ASC
    """, (sender_id, receiver_id, receiver_id, sender_id))
    messages = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(messages)

@app.route('/api/send_message', methods=['POST'])
def send_message():
    if 'user' not in session:
        return jsonify({"message":"Not logged in"}), 401

    data = request.json
    sender_id = session['user']['id']
    receiver_id = data.get('receiver_id')
    message = data.get('message')

    if not receiver_id or not message:
        return jsonify({"message":"Invalid data"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO messages (sender_id, receiver_id, message)
        VALUES (%s, %s, %s)
    """, (sender_id, receiver_id, message))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message":"Message sent successfully"})
@app.route('/export_payroll_pdf/<int:user_id>')
def export_payroll_pdf(user_id):
    if 'user' not in session:
        return "Not logged in", 401

    # Only allow employee for self, or admin/HR for any
    current_user = session['user']
    if current_user['role'].lower() == 'employee' and current_user['id'] != user_id:
        return "Unauthorized", 403

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch payroll records
    cursor.execute("""
        SELECT month, basic, bonus, total, COALESCE(status,'pending') AS status
        FROM payroll
        WHERE user_id=%s
        ORDER BY month DESC
    """, (user_id,))
    payrolls = cursor.fetchall()

    # Fetch user info
    cursor.execute("SELECT name, email FROM users WHERE id=%s", (user_id,))
    user = cursor.fetchone()
    conn.close()

    # Create HTML for PDF
    html = render_template_string("""
        <h2>Payroll Report for {{user.name}}</h2>
        <p>Email: {{user.email}}</p>
        <table border="1" cellspacing="0" cellpadding="5" style="width:100%; border-collapse:collapse;">
            <thead>
                <tr>
                    <th>Month</th>
                    <th>Basic</th>
                    <th>Bonus</th>
                    <th>Total</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
                {% for p in payrolls %}
                <tr>
                    <td>{{p.month}}</td>
                    <td>{{p.basic}}</td>
                    <td>{{p.bonus}}</td>
                    <td>{{p.total}}</td>
                    <td>{{p.status}}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    """, payrolls=payrolls, user=user)

    pdf = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=pdf)
    if pisa_status.err:
        return "Error generating PDF", 500

    pdf.seek(0)
    response = make_response(pdf.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=payroll_{user["name"]}.pdf'
    return response
@app.route('/api/holidays')
def get_holidays():
    holidays = [
        {"title": "Republic Day", "date": "2025-01-26"},
        {"title": "Independence Day", "date": "2025-08-15"},
        {"title": "Gandhi Jayanti", "date": "2025-10-02"},
        {"title": "Ugadi", "date": "2025-03-30"},
        {"title": "Sankranti", "date": "2025-01-14"},
        {"title": "Vinayaka Chavithi", "date": "2025-09-09"},
        {"title": "Deepavali", "date": "2025-11-01"},
        {"title": "Vijayadashami", "date": "2025-10-02"}
    ]
    return jsonify(holidays)
# ------------------- PROJECTS -------------------
@app.route('/api/projects')
def get_projects():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM projects ORDER BY created_at DESC")
    projects = cursor.fetchall()

    for project in projects:
        # Fetch assigned employees
        cursor.execute("""
            SELECT u.id, u.name
            FROM project_assignments pa
            JOIN users u ON pa.user_id = u.id
            WHERE pa.project_id=%s
        """, (project['id'],))
        project['employees'] = cursor.fetchall()  # <--- this is the key
        # optional: remove assigned_to string if you want
        # del project['assigned_to']

    cursor.close()
    conn.close()
    return jsonify(projects)

# Flask example
@app.route('/api/projects', methods=['POST'])
def add_project():
    data = request.get_json()
    name = data['name']
    status = data['status']
    priority = data['priority']
    description = data['description']
    employee_ids = data['employees']  # list of user IDs

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # --- Get names of selected users ---
    if employee_ids:
        format_strings = ','.join(['%s'] * len(employee_ids))
        cursor.execute(f"SELECT name FROM users WHERE id IN ({format_strings})", tuple(employee_ids))
        assigned_names = [row['name'] for row in cursor.fetchall()]
        assigned_to_str = ", ".join(assigned_names)
    else:
        assigned_to_str = ""

    # --- Insert project ---
    cursor.execute("""
        INSERT INTO projects (name, status, priority, description, assigned_to)
        VALUES (%s, %s, %s, %s, %s)
    """, (name, status, priority, description, assigned_to_str))

    project_id = cursor.lastrowid

    # --- Also insert into project_assignments if you want to keep mapping ---
    for emp_id in employee_ids:
        cursor.execute("INSERT INTO project_assignments (project_id,user_id) VALUES (%s,%s)", (project_id, emp_id))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({'message': 'Project added successfully'})



@app.route('/api/projects/<int:project_id>', methods=['DELETE'])
def delete_project(project_id):
    if 'user' not in session or session['user']['role'].lower() not in ['admin', 'manager', 'hr']:
        return jsonify({"message": "Unauthorized"}), 403
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM projects WHERE id=%s", (project_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Project deleted successfully"})
@app.route('/api/projects/<int:project_id>/assign', methods=['POST'])
def assign_users(project_id):
    data = request.json
    user_ids = data.get('user_ids', [])

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Delete old assignments
    cursor.execute("DELETE FROM project_assignments WHERE project_id=%s", (project_id,))

    # Insert new assignments
    for uid in user_ids:
        cursor.execute("INSERT INTO project_assignments (project_id, user_id) VALUES (%s, %s)", (project_id, uid))

    # Update assigned_to column
    if user_ids:
        format_strings = ','.join(['%s'] * len(user_ids))
        cursor.execute(f"SELECT name FROM users WHERE id IN ({format_strings})", tuple(user_ids))
        assigned_names = [row['name'] for row in cursor.fetchall()]
        assigned_to_str = ", ".join(assigned_names)
    else:
        assigned_to_str = ""
    cursor.execute("UPDATE projects SET assigned_to=%s WHERE id=%s", (assigned_to_str, project_id))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Users assigned successfully"})


@app.route('/api/projects/<int:project_id>/users')
def get_project_users(project_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT u.id, u.name, u.email
        FROM project_assignments pa
        JOIN users u ON pa.user_id = u.id
        WHERE pa.project_id=%s
    """, (project_id,))
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(users)
# Get all users (for dropdown in frontend)
@app.route('/api/users/all')
def get_users_for_dropdown():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name FROM users WHERE role != 'admin'")
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(users)

# Assign employee to project
@app.route('/api/assign_project', methods=['POST'])
def assign_project():
    data = request.json
    project_id = data['project_id']
    user_id = data['user_id']

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO project_assignments (project_id, user_id) VALUES (%s, %s)", (project_id, user_id))
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Employee assigned successfully"})

# Get assigned employees for a project
@app.route('/api/project_employees/<int:project_id>')
def project_employees(project_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    query = """
        SELECT u.id, u.name, u.email 
        FROM project_assignments pa
        JOIN users u ON pa.user_id = u.id
        WHERE pa.project_id = %s
    """
    cursor.execute(query, (project_id,))
    employees = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(employees)
# ----------------- DEPARTMENT MANAGEMENT -----------------

@app.route('/api/departments', methods=['GET'])
def get_departments():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT d.id, d.name FROM departments d")
    departments = cursor.fetchall()

    result = []
    for d in departments:
        cursor.execute("""
            SELECT u.id, u.name 
            FROM department_employees de
            JOIN users u ON de.employee_id = u.id
            WHERE de.department_id = %s
        """, (d['id'],))
        employees = cursor.fetchall()
        d['employees'] = employees
        result.append(d)
    cursor.close()
    conn.close()
    return jsonify(result)


@app.route('/api/departments/<int:id>', methods=['GET'])
def get_department(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name FROM departments WHERE id=%s", (id,))
    dept = cursor.fetchone()
    if not dept:
        return jsonify({"error": "Department not found"}), 404

    cursor.execute("""
        SELECT u.id, u.name 
        FROM department_employees de
        JOIN users u ON de.employee_id = u.id
        WHERE de.department_id = %s
    """, (id,))
    dept['employees'] = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(dept)


@app.route('/api/departments', methods=['POST'])
def add_department():
    data = request.json
    name = data['name']
    employees = data.get('employees', [])

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO departments (name) VALUES (%s)", (name,))
    dept_id = cursor.lastrowid

    for emp_id in employees:
        cursor.execute("INSERT INTO department_employees (department_id, employee_id) VALUES (%s, %s)", (dept_id, emp_id))

    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Department added"})


@app.route('/api/departments/<int:id>', methods=['PUT'])
def update_department(id):
    data = request.json
    name = data['name']
    employees = data.get('employees', [])

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE departments SET name=%s WHERE id=%s", (name, id))
    cursor.execute("DELETE FROM department_employees WHERE department_id=%s", (id,))
    for emp_id in employees:
        cursor.execute("INSERT INTO department_employees (department_id, employee_id) VALUES (%s, %s)", (id, emp_id))

    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Department updated"})


@app.route('/api/departments/<int:id>', methods=['DELETE'])
def delete_department(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM department_employees WHERE department_id=%s", (id,))
    cursor.execute("DELETE FROM departments WHERE id=%s", (id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Department deleted"})
@app.route('/api/attendance_trend')
@app.route('/api/attendance_trend')
def attendance_trend():
    if 'user' not in session:
        return jsonify({"message": "Not logged in"}), 401
    
    user_id = session['user']['id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT date, status 
        FROM attendance 
        WHERE user_id=%s 
        ORDER BY date ASC
    """, (user_id,))
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(data)
@app.route('/api/work_logs')
def get_work_logs():
    month = request.args.get('month')  # ex: "2025-09"
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if month:
        cursor.execute("""
            SELECT w.id, u.name, w.log_date, w.clock_in, w.clock_out
            FROM work_logs w
            JOIN users u ON w.user_id = u.id
            WHERE DATE_FORMAT(w.log_date, '%Y-%m') = %s
            ORDER BY w.log_date DESC
        """, (month,))
    else:
        cursor.execute("""
            SELECT w.id, u.name, w.log_date, w.clock_in, w.clock_out
            FROM work_logs w
            JOIN users u ON w.user_id = u.id
            ORDER BY w.log_date DESC
        """)

    rows = cursor.fetchall()
    logs = []
    for r in rows:
        logs.append({
            'id': r['id'],
            'name': r['name'],
            'log_date': r['log_date'].strftime("%Y-%m-%d") if r['log_date'] else '',
            'clock_in': r['clock_in'].strftime("%H:%M:%S") if r['clock_in'] else '',
            'clock_out': r['clock_out'].strftime("%H:%M:%S") if r['clock_out'] else ''
        })

    cursor.close()
    conn.close()
    return jsonify(logs)

@app.route('/api/projects/<int:project_id>', methods=['PUT'])
def edit_project(project_id):
    if 'user' not in session or session['user']['role'].lower() not in ['admin', 'manager', 'hr']:
        return jsonify({"message": "Unauthorized"}), 403

    data = request.get_json()
    name = data.get('name')
    status = data.get('status')
    priority = data.get('priority')
    description = data.get('description')
    employee_ids = data.get('employees', [])  # list of assigned user IDs

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Update project details
    cursor.execute("""
        UPDATE projects
        SET name=%s, status=%s, priority=%s, description=%s
        WHERE id=%s
    """, (name, status, priority, description, project_id))

    # Update assignments
    cursor.execute("DELETE FROM project_assignments WHERE project_id=%s", (project_id,))
    for emp_id in employee_ids:
        cursor.execute("INSERT INTO project_assignments (project_id, user_id) VALUES (%s, %s)", (project_id, emp_id))

    # Update assigned_to column for display
    if employee_ids:
        format_strings = ','.join(['%s'] * len(employee_ids))
        cursor.execute(f"SELECT name FROM users WHERE id IN ({format_strings})", tuple(employee_ids))
        assigned_names = [row['name'] for row in cursor.fetchall()]
        assigned_to_str = ", ".join(assigned_names)
    else:
        assigned_to_str = ""
    cursor.execute("UPDATE projects SET assigned_to=%s WHERE id=%s", (assigned_to_str, project_id))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Project updated successfully"})
@app.route('/api/projects/<int:id>', methods=['GET'])
def get_project(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM projects WHERE id = %s", (id,))
    project = cursor.fetchone()
    cursor.close()
    conn.close()
    return jsonify(project)


def get_all_leads():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM leads ORDER BY id DESC")
    leads = cursor.fetchall()
    conn.close()
    return leads

def add_new_lead(data):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO leads (name, email, phone, status, source) VALUES (%s,%s,%s,%s,%s)", 
        (data.get('name',''), data.get('email',''), data.get('phone',''), data.get('status','Active'), data.get('source',''))
    )
    conn.commit()
    conn.close()

@app.route('/api/leads', methods=['GET','POST'])
def leads():
    if 'user' not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 401

    if request.method == 'GET':
        return jsonify(get_all_leads())

    data = request.json
    add_new_lead(data)
    return jsonify({"success": True, "message":"Lead added successfully"})

# ------------------- EDIT LEAD -------------------
@app.route('/edit_lead/<int:lead_id>', methods=['PUT'])
def edit_lead(lead_id):
    if 'user' not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 401
    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE leads SET name=%s, email=%s, phone=%s, source=%s WHERE id=%s",
        (data.get('name',''), data.get('email',''), data.get('phone',''), data.get('source',''), lead_id)
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Lead updated successfully"})

# ------------------- DELETE LEAD -------------------
@app.route('/delete_lead/<int:lead_id>', methods=['DELETE'])
def delete_lead(lead_id):
    if 'user' not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 401
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM leads WHERE id=%s", (lead_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Lead deleted successfully"})

# ------------------- FILE UPLOAD -------------------
@app.route('/upload_file', methods=['POST'])
def upload_file():
    if 'user' not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 401

    file = request.files.get('file')
    if not file or not allowed_file(file.filename):
        return jsonify({"success": False, "message": "Invalid or no file uploaded"}), 400

    filename = secure_filename(file.filename)
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(save_path)
    file_ext = filename.rsplit('.', 1)[1].lower()

    if file_ext in ['csv', 'xlsx', 'xls']:
        try:
            df = pd.read_csv(save_path, encoding='utf-8') if file_ext=='csv' else pd.read_excel(save_path)
            df.columns = [str(c).strip().lower() for c in df.columns]

            col_map = {}
            for c in df.columns:
                if 'name' in c: col_map['name']=c
                elif 'email' in c: col_map['email']=c
                elif 'phone' in c: col_map['phone']=c
                elif 'source' in c: col_map['source']=c

            conn = get_db_connection()
            cursor = conn.cursor()
            count = 0

            # ----- FIXED INDENTATION -----
            for _, row in df.iterrows():
                name = str(row.get(col_map.get('name',''),'')).strip()
                email = str(row.get(col_map.get('email',''),'')).strip()
                phone = str(row.get(col_map.get('phone',''),'')).strip().replace('.0','')
                source = str(row.get(col_map.get('source',''),'')).strip()

                print(f"DEBUG: {name}, {email}, {phone}, {source}")  # <-- Debug terminal

                cursor.execute(
                    "INSERT INTO leads (name,email,phone,source,status) VALUES (%s,%s,%s,%s,%s)",
                    (name, email, phone, source, "Active")
                )
                count += 1

            conn.commit()
            conn.close()
            return jsonify({"success": True, "message": f"{count} leads uploaded successfully"})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500

    return jsonify({"success": True, "message": f"File '{filename}' uploaded successfully"})

@app.route('/download_payslip/<int:payroll_id>')
def download_payslip(payroll_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM payroll WHERE id=%s", (payroll_id,))
    payroll = cursor.fetchone()
    if not payroll:
        return "Payroll not found", 404

    cursor.execute("SELECT * FROM users WHERE id=%s", (payroll['user_id'],))
    user = cursor.fetchone()
    if not user:
        return "User not found", 404

    html = f"""
    <html>
    <head>
      <style>
        body {{ font-family: Arial, sans-serif; }}
        .payslip {{ width: 600px; margin: auto; border: 1px solid #000; padding: 20px; }}
        h2 {{ text-align:center; }}
        table {{ width:100%; border-collapse: collapse; margin-top:20px; }}
        td, th {{ border:1px solid #000; padding: 8px; text-align:left; }}
      </style>
    </head>
    <body>
      <div class="payslip">
        <h2>Payslip - {payroll['month']}</h2>
        <p><strong>Name:</strong> {user['name']}</p>
        <p><strong>Email:</strong> {user['email']}</p>
        <p><strong>Role:</strong> {user['role']}</p>

        <table>
          <tr>
            <th>Basic</th>
            <th>Bonus</th>
            <th>Total</th>
            <th>Status</th>
          </tr>
          <tr>
            <td>{payroll['basic']}</td>
            <td>{payroll['bonus']}</td>
            <td>{payroll['total']}</td>
            <td>{payroll['status']}</td>
          </tr>
        </table>
      </div>
    </body>
    </html>
    """

    pdf = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=pdf)
    if pisa_status.err:
        return "Error generating PDF", 500

    pdf.seek(0)
    filename = f"Payslip_{user['name']}_{payroll['month']}.pdf"

    # Important: use download_name and set as_attachment=True
    return send_file(
        pdf,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )
@app.route('/api/my_documents')
def my_documents():
    if 'user' not in session:
        return jsonify([])  # not logged in

    user_id = session['user']['id']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT documents FROM users WHERE id=%s", (user_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    docs = []
    if row and row['documents']:
        import json
        try:
            filenames = json.loads(row['documents'])  # ["file1.pdf", "file2.jpg"]
            for i, f in enumerate(filenames):
                docs.append({
                    "id": i+1,
                    "name": f,
                    "path": f"/static/uploads/{f}"
                })
        except:
            pass

    return jsonify(docs)


if __name__ == '__main__':
    app.run(debug=True)
