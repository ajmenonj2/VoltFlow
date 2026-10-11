from flask import Flask, render_template, request, jsonify, session, redirect
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, os
from functools import wraps
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('VOLTFlow_DB', os.path.join(BASE, 'voltflow.db'))
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-development-secret-key')

SCHEMA = '''
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (
 user_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
 password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('Admin','Station Operator','Maintenance Staff','EV Owner')),
 phone TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS vehicles (
 vehicle_no TEXT PRIMARY KEY, model TEXT NOT NULL, user_id INTEGER NOT NULL,
 FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS charging_stations (
 station_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, location TEXT NOT NULL,
 total_chargers INTEGER NOT NULL DEFAULT 1 CHECK(total_chargers > 0), price_per_kwh REAL NOT NULL DEFAULT 18 CHECK(price_per_kwh >= 0)
);
CREATE TABLE IF NOT EXISTS chargers (
 charger_id INTEGER PRIMARY KEY AUTOINCREMENT, station_id INTEGER NOT NULL,
 type TEXT NOT NULL DEFAULT 'AC', status TEXT NOT NULL DEFAULT 'Available' CHECK(status IN ('Available','Busy','Maintenance','Offline')),
 FOREIGN KEY(station_id) REFERENCES charging_stations(station_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS reservations (
 reservation_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, vehicle_no TEXT NOT NULL,
 station_id INTEGER NOT NULL, slot_time TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'Confirmed' CHECK(status IN ('Confirmed','Pending','Cancelled','Completed')),
 remarks TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(user_id) REFERENCES users(user_id), FOREIGN KEY(vehicle_no) REFERENCES vehicles(vehicle_no),
 FOREIGN KEY(station_id) REFERENCES charging_stations(station_id)
);
CREATE TABLE IF NOT EXISTS charging_sessions (
 session_id INTEGER PRIMARY KEY AUTOINCREMENT, reservation_id INTEGER NOT NULL UNIQUE, charger_id INTEGER NOT NULL,
 energy_kwh REAL NOT NULL DEFAULT 0 CHECK(energy_kwh >= 0), duration_minutes INTEGER NOT NULL DEFAULT 0,
 start_time TEXT, end_time TEXT, status TEXT NOT NULL DEFAULT 'Waiting' CHECK(status IN ('Waiting','Charging','Completed')),
 FOREIGN KEY(reservation_id) REFERENCES reservations(reservation_id), FOREIGN KEY(charger_id) REFERENCES chargers(charger_id)
);
CREATE TABLE IF NOT EXISTS payments (
 payment_id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER NOT NULL UNIQUE, amount REAL NOT NULL CHECK(amount >= 0),
 method TEXT NOT NULL DEFAULT 'UPI' CHECK(method IN ('UPI','Card','Cash','Net Banking','Wallet')),
 payment_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, status TEXT NOT NULL DEFAULT 'Pending' CHECK(status IN ('Pending','Paid','Failed')),
 FOREIGN KEY(session_id) REFERENCES charging_sessions(session_id)
);
CREATE TABLE IF NOT EXISTS maintenance_records (
 maintenance_id INTEGER PRIMARY KEY AUTOINCREMENT, station_id INTEGER NOT NULL, technician_id INTEGER NOT NULL,
 maintenance_date TEXT NOT NULL, priority TEXT NOT NULL CHECK(priority IN ('Low','Medium','High','Critical')),
 description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Scheduled' CHECK(status IN ('Scheduled','In Progress','Completed')),
 FOREIGN KEY(station_id) REFERENCES charging_stations(station_id), FOREIGN KEY(technician_id) REFERENCES users(user_id)
);
CREATE INDEX IF NOT EXISTS idx_reservations_slot ON reservations(station_id, slot_time);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON charging_sessions(status);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);
'''

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys = ON')
    return con

def init_db():
    con = db(); con.executescript(SCHEMA)
    if not con.execute('SELECT 1 FROM users LIMIT 1').fetchone():
        con.execute('INSERT INTO users(name,email,password_hash,role,phone) VALUES(?,?,?,?,?)', ('VoltFlow Admin','admin@voltflow.in',generate_password_hash('Admin@123'),'Admin','9000000000'))
        con.execute('INSERT INTO users(name,email,password_hash,role,phone) VALUES(?,?,?,?,?)', ('Demo EV Owner','owner@voltflow.in',generate_password_hash('Owner@123'),'EV Owner','9000000001'))
        con.execute('INSERT INTO users(name,email,password_hash,role,phone) VALUES(?,?,?,?,?)', ('Demo Technician','tech@voltflow.in',generate_password_hash('Tech@123'),'Maintenance Staff','9000000002'))
        stations = [('Thrissur Central Hub','Thrissur, Kerala',8,18),('Kochi Fast Charge','Kochi, Kerala',6,21),('Calicut EV Point','Kozhikode, Kerala',5,19),('Trivandrum SuperCharge','Thiruvananthapuram, Kerala',7,20)]
        for name,loc,count,price in stations:
            cur=con.execute('INSERT INTO charging_stations(name,location,total_chargers,price_per_kwh) VALUES(?,?,?,?)',(name,loc,count,price)); sid=cur.lastrowid
            for i in range(count): con.execute('INSERT INTO chargers(station_id,type,status) VALUES(?,?,?)',(sid,'DC Fast' if i%2 else 'AC','Busy' if i==0 and sid==1 else 'Available'))
        owner=con.execute("SELECT user_id FROM users WHERE email='owner@voltflow.in'").fetchone()['user_id']
        con.execute('INSERT INTO vehicles(vehicle_no,model,user_id) VALUES(?,?,?)',('KL01AB1234','Tata Nexon EV',owner))
        con.commit()
    con.close()

@app.before_request
def setup(): init_db()

def login_required(fn):
    @wraps(fn)
    def wrapper(*args,**kwargs):
        if 'user_id' not in session: return jsonify({'error':'Please log in first.'}),401
        return fn(*args,**kwargs)
    return wrapper

def role_required(*roles):
    def dec(fn):
        @wraps(fn)
        def wrapper(*args,**kwargs):
            if 'user_id' not in session: return jsonify({'error':'Please log in first.'}),401
            if session.get('role') not in roles: return jsonify({'error':'Your role is not allowed to perform this action.'}),403
            return fn(*args,**kwargs)
        return wrapper
    return dec

def rows(sql, args=()):
    con=db()
    try: return [dict(r) for r in con.execute(sql,args).fetchall()]
    finally: con.close()

def one(sql,args=()):
    result=rows(sql,args); return result[0] if result else None

@app.route('/')
def index(): return render_template('index.html')

@app.post('/api/login')
def login():
    data=request.get_json(force=True); email=data.get('email','').strip().lower(); password=data.get('password','')
    user=one('SELECT * FROM users WHERE email=?',(email,))
    if not user or not check_password_hash(user['password_hash'],password): return jsonify({'error':'Invalid email or password.'}),401
    session.clear(); session['user_id']=user['user_id']; session['name']=user['name']; session['email']=user['email']; session['role']=user['role']
    return jsonify({'user':{'user_id':user['user_id'],'name':user['name'],'email':user['email'],'role':user['role']}})

@app.post('/api/register')
def register():
    d=request.get_json(force=True); name=d.get('name','').strip(); email=d.get('email','').strip().lower(); password=d.get('password',''); phone=d.get('phone','').strip()
    if not name or not email or len(password)<8: return jsonify({'error':'Name, email and a password of at least 8 characters are required.'}),400
    con=db()
    try:
        cur=con.execute('INSERT INTO users(name,email,password_hash,role,phone) VALUES(?,?,?,?,?)',(name,email,generate_password_hash(password),'EV Owner',phone)); con.commit()
        session.clear(); session['user_id']=cur.lastrowid; session['name']=name; session['email']=email; session['role']='EV Owner'
        return jsonify({'user':{'user_id':cur.lastrowid,'name':name,'email':email,'role':'EV Owner'}}),201
    except sqlite3.IntegrityError: return jsonify({'error':'An account with this email already exists.'}),409
    finally: con.close()

@app.post('/api/logout')
def logout(): session.clear(); return jsonify({'ok':True})
@app.get('/api/me')
def me():
    if 'user_id' not in session: return jsonify({'user':None})
    return jsonify({'user':{k:session[k] for k in ('user_id','name','email','role')}})

@app.get('/api/dashboard')
@login_required
def dashboard():
    return jsonify({
      'station_count':one('SELECT COUNT(*) n FROM charging_stations')['n'],
      'charger_count':one('SELECT COUNT(*) n FROM chargers')['n'],
      'available_chargers':one("SELECT COUNT(*) n FROM chargers WHERE status='Available'")['n'],
      'active_sessions':one("SELECT COUNT(*) n FROM charging_sessions WHERE status='Charging'")['n'],
      'energy_kwh':one("SELECT COALESCE(SUM(energy_kwh),0) n FROM charging_sessions")['n'],
      'revenue':one("SELECT COALESCE(SUM(amount),0) n FROM payments WHERE status='Paid'")['n'],
      'pending_payments':one("SELECT COUNT(*) n FROM payments WHERE status='Pending'")['n'],
      'reservations':one("SELECT COUNT(*) n FROM reservations WHERE status!='Cancelled'")['n'],
      'recent_sessions':rows('''SELECT cs.session_id,cs.energy_kwh,cs.status,cs.start_time,cs.end_time, r.vehicle_no,s.name station_name,u.name owner_name FROM charging_sessions cs JOIN reservations r ON r.reservation_id=cs.reservation_id JOIN charging_stations s ON s.station_id=r.station_id JOIN users u ON u.user_id=r.user_id ORDER BY cs.session_id DESC LIMIT 6''')
    })

@app.get('/api/stations')
@login_required
def get_stations():
    return jsonify(rows('''SELECT s.station_id,s.name,s.location,s.total_chargers,s.price_per_kwh,
      SUM(CASE WHEN c.status='Available' THEN 1 ELSE 0 END) available,
      SUM(CASE WHEN c.status='Busy' THEN 1 ELSE 0 END) busy,
      SUM(CASE WHEN c.status='Maintenance' THEN 1 ELSE 0 END) maintenance
      FROM charging_stations s LEFT JOIN chargers c ON c.station_id=s.station_id GROUP BY s.station_id ORDER BY s.station_id'''))

@app.post('/api/stations')
@role_required('Admin','Station Operator')
def add_station():
    d=request.get_json(force=True); name=d.get('name','').strip(); loc=d.get('location','').strip(); count=int(d.get('total_chargers',1)); price=float(d.get('price_per_kwh',18))
    if not name or not loc or count<1 or price<0: return jsonify({'error':'Enter a station name, location, positive charger count and valid tariff.'}),400
    con=db()
    try:
        cur=con.execute('INSERT INTO charging_stations(name,location,total_chargers,price_per_kwh) VALUES(?,?,?,?)',(name,loc,count,price))
        for i in range(count): con.execute('INSERT INTO chargers(station_id,type,status) VALUES(?,?,?)',(cur.lastrowid,d.get('charger_type','AC'),'Available'))
        con.commit(); return jsonify({'ok':True,'station_id':cur.lastrowid}),201
    finally: con.close()

@app.get('/api/vehicles')
@login_required
def get_vehicles():
    if session['role']=='EV Owner': return jsonify(rows('SELECT v.*,u.name owner_name FROM vehicles v JOIN users u ON u.user_id=v.user_id WHERE v.user_id=? ORDER BY v.vehicle_no',(session['user_id'],)))
    return jsonify(rows('SELECT v.*,u.name owner_name FROM vehicles v JOIN users u ON u.user_id=v.user_id ORDER BY v.vehicle_no'))

@app.post('/api/vehicles')
@role_required('EV Owner','Admin')
def add_vehicle():
    d=request.get_json(force=True); plate=d.get('vehicle_no','').strip().upper(); model=d.get('model','').strip(); uid=session['user_id']
    if session['role']=='Admin' and d.get('user_id'): uid=int(d['user_id'])
    if not plate or not model: return jsonify({'error':'Vehicle number and model are required.'}),400
    try:
        con=db(); con.execute('INSERT INTO vehicles(vehicle_no,model,user_id) VALUES(?,?,?)',(plate,model,uid)); con.commit(); con.close(); return jsonify({'ok':True}),201
    except sqlite3.IntegrityError: return jsonify({'error':'Vehicle number already exists or owner is invalid.'}),409

@app.get('/api/users')
@role_required('Admin','Station Operator')
def get_users(): return jsonify(rows('SELECT user_id,name,email,role,phone FROM users ORDER BY name'))

@app.get('/api/technicians')
@login_required
def get_technicians(): return jsonify(rows("SELECT user_id,name FROM users WHERE role='Maintenance Staff' ORDER BY name"))

@app.get('/api/reservations')
@login_required
def get_reservations():
    base='''SELECT r.reservation_id,r.user_id,r.vehicle_no,r.station_id,r.slot_time,r.status,r.remarks,u.name owner_name,s.name station_name FROM reservations r JOIN users u ON u.user_id=r.user_id JOIN charging_stations s ON s.station_id=r.station_id'''
    if session['role']=='EV Owner': return jsonify(rows(base+' WHERE r.user_id=? ORDER BY r.slot_time DESC',(session['user_id'],)))
    return jsonify(rows(base+' ORDER BY r.slot_time DESC'))

@app.post('/api/reservations')
@role_required('EV Owner','Admin','Station Operator')
def add_reservation():
    d=request.get_json(force=True); plate=d.get('vehicle_no','').strip().upper(); slot=d.get('slot_time','').strip(); station=d.get('station_id'); remarks=d.get('remarks','').strip()
    if not plate or not slot or not station: return jsonify({'error':'Vehicle, station and slot time are required.'}),400
    uid=session['user_id']
    con=db()
    try:
        v=con.execute('SELECT user_id FROM vehicles WHERE vehicle_no=?',(plate,)).fetchone()
        if not v: return jsonify({'error':'Vehicle not found. Add the vehicle first.'}),400
        if session['role']=='EV Owner' and v['user_id']!=uid: return jsonify({'error':'You can only reserve using your own vehicle.'}),403
        if session['role']!='EV Owner': uid=int(d.get('user_id',v['user_id']))
        dt=datetime.fromisoformat(slot)
        if dt < datetime.now(): return jsonify({'error':'Reservation time must be in the future.'}),400
        conflict=con.execute("SELECT 1 FROM reservations WHERE station_id=? AND slot_time=? AND status IN ('Confirmed','Pending')",(station,slot)).fetchone()
        if conflict: return jsonify({'error':'This station already has a reservation at that exact slot. Choose another time.'}),409
        cur=con.execute("INSERT INTO reservations(user_id,vehicle_no,station_id,slot_time,status,remarks) VALUES(?,?,?,?, 'Confirmed',?)",(uid,plate,station,slot,remarks)); con.commit()
        return jsonify({'ok':True,'reservation_id':cur.lastrowid}),201
    except ValueError: return jsonify({'error':'Invalid date/time format.'}),400
    except sqlite3.IntegrityError: return jsonify({'error':'Invalid user, vehicle or station.'}),400
    finally: con.close()

@app.patch('/api/reservations/<int:rid>')
@login_required
def update_reservation(rid):
    d=request.get_json(force=True); status=d.get('status')
    if status not in ('Pending','Confirmed','Cancelled','Completed'): return jsonify({'error':'Invalid reservation status.'}),400
    con=db(); row=con.execute('SELECT user_id FROM reservations WHERE reservation_id=?',(rid,)).fetchone()
    if not row: con.close(); return jsonify({'error':'Reservation not found.'}),404
    if session['role']=='EV Owner' and row['user_id']!=session['user_id']: con.close(); return jsonify({'error':'Not your reservation.'}),403
    con.execute('UPDATE reservations SET status=? WHERE reservation_id=?',(status,rid)); con.commit(); con.close(); return jsonify({'ok':True})

@app.get('/api/sessions')
@login_required
def get_sessions():
    sql='''SELECT cs.session_id,cs.reservation_id,cs.charger_id,cs.energy_kwh,cs.duration_minutes,cs.start_time,cs.end_time,cs.status,r.vehicle_no,r.user_id,u.name owner_name,s.name station_name,c.type charger_type FROM charging_sessions cs JOIN reservations r ON r.reservation_id=cs.reservation_id JOIN users u ON u.user_id=r.user_id JOIN charging_stations s ON s.station_id=r.station_id JOIN chargers c ON c.charger_id=cs.charger_id'''
    if session['role']=='EV Owner': return jsonify(rows(sql+' WHERE r.user_id=? ORDER BY cs.session_id DESC',(session['user_id'],)))
    return jsonify(rows(sql+' ORDER BY cs.session_id DESC'))

@app.post('/api/sessions/start')
@role_required('Admin','Station Operator')
def start_session():
    d=request.get_json(force=True); rid=int(d.get('reservation_id',0)); con=db()
    try:
        r=con.execute("SELECT * FROM reservations WHERE reservation_id=? AND status='Confirmed'",(rid,)).fetchone()
        if not r: return jsonify({'error':'A confirmed reservation is required.'}),400
        if con.execute('SELECT 1 FROM charging_sessions WHERE reservation_id=?',(rid,)).fetchone(): return jsonify({'error':'A session already exists for this reservation.'}),409
        charger=con.execute("SELECT c.charger_id FROM chargers c WHERE c.station_id=? AND c.status='Available' LIMIT 1",(r['station_id'],)).fetchone()
        if not charger: return jsonify({'error':'No available charger at this station.'}),409
        now=datetime.now().isoformat(timespec='minutes')
        cur=con.execute("INSERT INTO charging_sessions(reservation_id,charger_id,start_time,status) VALUES(?,?,?,'Charging')",(rid,charger['charger_id'],now))
        con.execute("UPDATE chargers SET status='Busy' WHERE charger_id=?",(charger['charger_id'],)); con.commit(); return jsonify({'ok':True,'session_id':cur.lastrowid}),201
    finally: con.close()

@app.patch('/api/sessions/<int:sid>/complete')
@role_required('Admin','Station Operator')
def complete_session(sid):
    d=request.get_json(force=True)
    try: energy=float(d.get('energy_kwh',0)); rate_method=d.get('method','UPI')
    except (TypeError,ValueError): return jsonify({'error':'Energy must be numeric.'}),400
    if energy<0 or rate_method not in ('UPI','Card','Cash','Net Banking','Wallet'): return jsonify({'error':'Invalid energy or payment method.'}),400
    con=db()
    try:
        s=con.execute('''SELECT cs.*,c.charger_id,c.station_id,st.price_per_kwh,r.reservation_id FROM charging_sessions cs JOIN chargers c ON c.charger_id=cs.charger_id JOIN charging_stations st ON st.station_id=c.station_id JOIN reservations r ON r.reservation_id=cs.reservation_id WHERE cs.session_id=?''',(sid,)).fetchone()
        if not s: return jsonify({'error':'Session not found.'}),404
        if s['status']=='Completed': return jsonify({'error':'Session is already completed.'}),409
        end=datetime.now(); start=datetime.fromisoformat(s['start_time']) if s['start_time'] else end
        duration=max(0,int((end-start).total_seconds()//60)); amount=round(energy*s['price_per_kwh'],2)
        con.execute("UPDATE charging_sessions SET energy_kwh=?,duration_minutes=?,end_time=?,status='Completed' WHERE session_id=?",(energy,duration,end.isoformat(timespec='minutes'),sid))
        con.execute("UPDATE chargers SET status='Available' WHERE charger_id=?",(s['charger_id'],))
        con.execute("UPDATE reservations SET status='Completed' WHERE reservation_id=?",(s['reservation_id'],))
        con.execute("INSERT INTO payments(session_id,amount,method,status) VALUES(?,?,?,'Pending') ON CONFLICT(session_id) DO NOTHING",(sid,amount,rate_method))
        con.commit(); return jsonify({'ok':True,'amount':amount,'duration_minutes':duration})
    finally: con.close()

@app.get('/api/payments')
@login_required
def get_payments():
    sql='''SELECT p.payment_id,p.session_id,p.amount,p.method,p.payment_date,p.status,cs.energy_kwh,r.vehicle_no,u.name owner_name,s.name station_name FROM payments p JOIN charging_sessions cs ON cs.session_id=p.session_id JOIN reservations r ON r.reservation_id=cs.reservation_id JOIN users u ON u.user_id=r.user_id JOIN charging_stations s ON s.station_id=r.station_id'''
    if session['role']=='EV Owner': return jsonify(rows(sql+' WHERE r.user_id=? ORDER BY p.payment_id DESC',(session['user_id'],)))
    return jsonify(rows(sql+' ORDER BY p.payment_id DESC'))

@app.patch('/api/payments/<int:pid>/pay')
@login_required
def pay_payment(pid):
    con=db(); p=con.execute('SELECT p.payment_id,r.user_id FROM payments p JOIN charging_sessions cs ON cs.session_id=p.session_id JOIN reservations r ON r.reservation_id=cs.reservation_id WHERE p.payment_id=?',(pid,)).fetchone()
    if not p: con.close(); return jsonify({'error':'Payment not found.'}),404
    if session['role']=='EV Owner' and p['user_id']!=session['user_id']: con.close(); return jsonify({'error':'Not your payment.'}),403
    con.execute("UPDATE payments SET status='Paid' WHERE payment_id=?",(pid,)); con.commit(); con.close(); return jsonify({'ok':True})

@app.get('/api/maintenance')
@login_required
def get_maintenance():
    return jsonify(rows('''SELECT m.maintenance_id,m.station_id,m.technician_id,m.maintenance_date,m.priority,m.description,m.status,s.name station_name,u.name technician_name FROM maintenance_records m JOIN charging_stations s ON s.station_id=m.station_id JOIN users u ON u.user_id=m.technician_id ORDER BY m.maintenance_id DESC'''))

@app.post('/api/maintenance')
@role_required('Admin','Station Operator','Maintenance Staff')
def add_maintenance():
    d=request.get_json(force=True)
    required=['station_id','technician_id','maintenance_date','priority','description']
    if any(not str(d.get(k,'')).strip() for k in required): return jsonify({'error':'All maintenance fields are required.'}),400
    if d['priority'] not in ('Low','Medium','High','Critical'): return jsonify({'error':'Invalid priority.'}),400
    con=db()
    try:
        cur=con.execute("INSERT INTO maintenance_records(station_id,technician_id,maintenance_date,priority,description,status) VALUES(?,?,?,?,?,'Scheduled')",(int(d['station_id']),int(d['technician_id']),d['maintenance_date'],d['priority'],d['description'].strip()))
        con.commit(); return jsonify({'ok':True,'maintenance_id':cur.lastrowid}),201
    except (sqlite3.IntegrityError,ValueError): return jsonify({'error':'Choose a valid station and maintenance technician.'}),400
    finally: con.close()

@app.patch('/api/maintenance/<int:mid>')
@role_required('Admin','Station Operator','Maintenance Staff')
def update_maintenance(mid):
    status=request.get_json(force=True).get('status')
    if status not in ('Scheduled','In Progress','Completed'): return jsonify({'error':'Invalid status.'}),400
    con=db(); cur=con.execute('UPDATE maintenance_records SET status=? WHERE maintenance_id=?',(status,mid)); con.commit(); con.close()
    if not cur.rowcount: return jsonify({'error':'Maintenance record not found.'}),404
    return jsonify({'ok':True})

@app.get('/api/reports')
@role_required('Admin','Station Operator')
def reports():
    return jsonify({'monthly':rows("SELECT strftime('%Y-%m',payment_date) month,ROUND(SUM(amount),2) revenue,COUNT(*) payments FROM payments WHERE status='Paid' GROUP BY strftime('%Y-%m',payment_date) ORDER BY month DESC LIMIT 6"),
      'station_usage':rows('''SELECT s.name,COUNT(cs.session_id) sessions,ROUND(COALESCE(SUM(cs.energy_kwh),0),2) energy_kwh,ROUND(COALESCE(SUM(CASE WHEN p.status='Paid' THEN p.amount ELSE 0 END),0),2) revenue FROM charging_stations s LEFT JOIN reservations r ON r.station_id=s.station_id LEFT JOIN charging_sessions cs ON cs.reservation_id=r.reservation_id LEFT JOIN payments p ON p.session_id=cs.session_id GROUP BY s.station_id ORDER BY revenue DESC''')})

@app.errorhandler(500)
def internal_error(e): return jsonify({'error':'Unexpected server error. Check the terminal for details.'}),500

if __name__ == '__main__':
    init_db()
    print('VoltFlow running at http://127.0.0.1:5000')
    print('Demo admin: admin@voltflow.in / Admin@123')
    app.run(debug=True)

from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True)