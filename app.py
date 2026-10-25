from flask import Flask, render_template, request, redirect, url_for, session
import psycopg2

app = Flask(__name__)
app.secret_key = 'llave_secreta_larphub'
DB_HOST = "localhost"
DB_NAME = "larphub"
DB_USER = "postgres"
DB_PASS = "Milorayo2012!"

def get_db_connection():
    conn = psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        client_encoding='utf8'
    )
    return conn

@app.route('/')
def inicio():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM usuarios WHERE username = %s AND password = %s", (username, password))
        user = cur.fetchone()
        cur.close()
        conn.close()
        
        if user:
            session['username'] = username
            return redirect(url_for('inicio'))
        else:
            return "Usuario o contraseña incorrectos."

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('inicio'))

@app.route('/profile/<nombre_usuario>')
def profile(nombre_usuario):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT username, biografia, estado, foto_perfil, cancion, css_personalizado FROM usuarios WHERE username = %s", 
        (nombre_usuario,)
    )
    usuario = cur.fetchone()
    cur.close()
    conn.close()

    if usuario:
        return render_template('profile.html', perfil=usuario)
    else:
        return "Este perfil no existe.", 404

@app.route('/edit_profile', methods=['GET', 'POST'])
def editar_perfil():
    if 'username' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        nueva_bio = request.form['biografia']
        nuevo_css = request.form['css_personalizado']
        nuevo_estado = request.form['estado']
        
        cur.execute(
            "UPDATE usuarios SET biografia = %s, css_personalizado = %s, estado = %s WHERE username = %s",
            (nueva_bio, nuevo_css, nuevo_estado, session['username'])
        )
        conn.commit()
        cur.close()
        conn.close()
        
        return redirect(url_for('profile', nombre_usuario=session['username']))

    cur.execute("SELECT biografia, css_personalizado, estado FROM usuarios WHERE username = %s", (session['username'],))
    datos_actuales = cur.fetchone()
    cur.close()
    conn.close()
    
    return render_template('edit_profile.html', datos=datos_actuales)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        try:
            cur.execute(
                "INSERT INTO usuarios (username, email, password) VALUES (%s, %s, %s)",
                (username, email, password)
            )
            conn.commit()
            cur.close()
            conn.close()
            
            return redirect(url_for('login'))
            
        except Exception as e:
            return f"Hubo un error al registrar: {e}"

    return render_template('register.html')

@app.route('/browse')
def browse():
    return render_template('browse.html')

@app.route('/messages')
def messages():
    return render_template('messages.html')

@app.route('/blog')
def blog():
    return render_template('blog.html')

@app.route('/forum')
def forum():
    return render_template('forum.html')

@app.route('/groups')
def groups():
    return render_template('groups.html')

if __name__ == '__main__':
    app.run(debug=True)