from flask import Flask, render_template, request, redirect, url_for, session
from markupsafe import Markup
import psycopg2
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'llave_secreta_larphub'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
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


@app.context_processor
def inyectar_funciones_admin():
    admins = set()
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT username FROM usuarios WHERE es_admin = TRUE")
        admins = {fila[0] for fila in cur.fetchall()}
        cur.close()
        conn.close()
    except Exception:
        pass

    def badge(username):
        if username in admins:
            return Markup('<span style="background: #1a1a1a; color: #a855f7; border: 1px solid #3b1d5e; font-size: 0.75em; padding: 2px 8px; border-radius: 12px; margin-left: 6px; font-weight: bold; vertical-align: middle; display: inline-flex; align-items: center; gap: 4px;" title="Creador de LARP HUB">🐈‍⬛ Creador</span>')
        return ''

    es_creador = session.get('username') in admins
    return dict(badge=badge, es_creador=es_creador, lista_admins=admins)


@app.route('/')
def inicio():
    if 'username' in session:
        usuario_actual = session['username']
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT foto_perfil FROM usuarios WHERE username = %s", (usuario_actual,))
        data_usuario = cur.fetchone()
        
        if data_usuario and data_usuario[0]:
            foto_val = data_usuario[0]
            foto_path = foto_val if foto_val.startswith('/') else f"/static/{foto_val}"
        else:
            foto_path = url_for('static', filename='avatar.png')
            
        foto_usuario = (foto_path,)

        cur.execute("""
            SELECT a.id, a.usuario_origen, u.foto_perfil 
            FROM amistades a
            JOIN usuarios u ON a.usuario_origen = u.username
            WHERE a.usuario_destino = %s AND a.estado = 'pendiente'
        """, (usuario_actual,))
        solicitudes_pendientes = cur.fetchall()

        cur.execute("""
            SELECT u.username, u.foto_perfil
            FROM amistades a
            JOIN usuarios u ON (
                (a.usuario_origen = %s AND u.username = a.usuario_destino) OR
                (a.usuario_destino = %s AND u.username = a.usuario_origen)
            )
            WHERE a.estado = 'aceptada'
        """, (usuario_actual, usuario_actual))
        mis_amigos = cur.fetchall()

        amigos_nombres = {a[0] for a in mis_amigos}
        cur.execute("SELECT usuario_destino FROM amistades WHERE usuario_origen = %s AND estado = 'pendiente'", (usuario_actual,))
        pendientes_enviadas = {r[0] for r in cur.fetchall()}

        cur.execute("""
            SELECT p.id, p.autor, p.archivo, p.descripcion, TO_CHAR(p.fecha, 'DD/MM/YYYY HH24:MI'), u.foto_perfil
            FROM publicaciones p
            JOIN usuarios u ON p.autor = u.username
            ORDER BY p.fecha DESC
        """)
        pubs_raw = cur.fetchall()

        publicaciones = []
        for pub in pubs_raw:
            pub_id, autor = pub[0], pub[1]
            cur.execute("SELECT COUNT(*) FROM likes_publicacion WHERE publicacion_id = %s", (pub_id,))
            total_likes = cur.fetchone()[0]
            
            cur.execute("SELECT 1 FROM likes_publicacion WHERE publicacion_id = %s AND username = %s", (pub_id, usuario_actual))
            dio_like = cur.fetchone() is not None
                
            cur.execute("""
                SELECT c.autor, c.comentario, TO_CHAR(c.fecha, 'HH24:MI'), c.id
                FROM comentarios_publicacion c
                WHERE c.publicacion_id = %s
                ORDER BY c.fecha ASC
            """, (pub_id,))
            comentarios = cur.fetchall()

            if autor == usuario_actual:
                rel_autor = 'yo'
            elif autor in amigos_nombres:
                rel_autor = 'amigos'
            elif autor in pendientes_enviadas:
                rel_autor = 'pendiente'
            else:
                rel_autor = 'ninguna'

            foto_aut_val = pub[5]
            if foto_aut_val:
                foto_autor_final = foto_aut_val if foto_aut_val.startswith('/') else f"/static/{foto_aut_val}"
            else:
                foto_autor_final = url_for('static', filename='avatar.png')

            publicaciones.append({
                'id': pub_id,
                'autor': autor,
                'archivo': pub[2],
                'descripcion': pub[3],
                'fecha': pub[4],
                'foto_autor': foto_autor_final,
                'likes': total_likes,
                'dio_like': dio_like,
                'comentarios': comentarios,
                'rel_autor': rel_autor
            })
        
        cur.close()
        conn.close()

        return render_template(
            'index.html', 
            foto=foto_usuario, 
            solicitudes=solicitudes_pendientes, 
            amigos=mis_amigos,
            publicaciones=publicaciones
        )
    
    return render_template('index.html')


@app.route('/crear_publicacion', methods=['POST'])
def crear_publicacion():
    if 'username' not in session:
        return redirect(url_for('login'))
        
    archivo = request.files.get('archivo')
    descripcion = request.form.get('descripcion', '').strip()
    
    if archivo and archivo.filename != '':
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        filename = secure_filename(archivo.filename)
        ruta_guardado = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        archivo.save(ruta_guardado)
        ruta_archivo = f"/static/uploads/{filename}"
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO publicaciones (autor, archivo, descripcion) VALUES (%s, %s, %s)",
            (session['username'], ruta_archivo, descripcion)
        )
        conn.commit()
        cur.close()
        conn.close()
        
    return redirect(url_for('inicio'))


@app.route('/eliminar_publicacion/<int:pub_id>', methods=['POST'])
def eliminar_publicacion(pub_id):
    if 'username' not in session:
        return redirect(url_for('login'))
        
    usuario_actual = session['username']
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT autor FROM publicaciones WHERE id = %s", (pub_id,))
    pub = cur.fetchone()
    
    cur.execute("SELECT es_admin FROM usuarios WHERE username = %s", (usuario_actual,))
    res_admin = cur.fetchone()
    es_admin = res_admin[0] if res_admin else False
    
    if pub and (pub[0] == usuario_actual or es_admin):
        cur.execute("DELETE FROM likes_publicacion WHERE publicacion_id = %s", (pub_id,))
        cur.execute("DELETE FROM comentarios_publicacion WHERE publicacion_id = %s", (pub_id,))
        cur.execute("DELETE FROM publicaciones WHERE id = %s", (pub_id,))
        conn.commit()
        
    cur.close()
    conn.close()
    return redirect(url_for('inicio'))


@app.route('/like/<int:pub_id>', methods=['POST'])
def dar_like(pub_id):
    if 'username' not in session:
        return {'error': 'No autorizado'}, 401
        
    usuario = session['username']
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT id FROM likes_publicacion WHERE publicacion_id = %s AND username = %s", (pub_id, usuario))
    existe = cur.fetchone()
    
    if existe:
        cur.execute("DELETE FROM likes_publicacion WHERE id = %s", (existe[0],))
        dio_like = False
    else:
        cur.execute("INSERT INTO likes_publicacion (publicacion_id, username) VALUES (%s, %s)", (pub_id, usuario))
        dio_like = True
        
    conn.commit()
    
    cur.execute("SELECT COUNT(*) FROM likes_publicacion WHERE publicacion_id = %s", (pub_id,))
    total_likes = cur.fetchone()[0]
    
    cur.close()
    conn.close()
    
    return {'dio_like': dio_like, 'total_likes': total_likes}


@app.route('/comentar/<int:pub_id>', methods=['POST'])
def comentar_publicacion(pub_id):
    if 'username' not in session:
        return {'error': 'No autorizado'}, 401
        
    comentario = request.form.get('comentario', '').strip()
    if comentario:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO comentarios_publicacion (publicacion_id, autor, comentario) VALUES (%s, %s, %s)",
            (pub_id, session['username'], comentario)
        )
        conn.commit()
        
        cur.execute("SELECT TO_CHAR(CURRENT_TIMESTAMP, 'HH24:MI')")
        hora = cur.fetchone()[0]
        
        cur.close()
        conn.close()
        
        return {'autor': session['username'], 'comentario': comentario, 'fecha': hora}
        
    return {'error': 'Vacío'}, 400


@app.route('/compartir_post/<int:pub_id>', methods=['POST'])
def compartir_post(pub_id):
    if 'username' not in session:
        return {'error': 'No autorizado'}, 401
        
    destinatario = request.form.get('destinatario')
    remitente = session['username']
    
    if destinatario:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT autor, archivo, descripcion FROM publicaciones WHERE id = %s", (pub_id,))
        pub = cur.fetchone()
        
        if pub:
            texto_compartido = f"📲 Publicación de @{pub[0]}: {pub[2] if pub[2] else ''}"
            cur.execute(
                "INSERT INTO mensajes (remitente, destinatario, contenido, imagen) VALUES (%s, %s, %s, %s)",
                (remitente, destinatario, texto_compartido, pub[1])
            )
            conn.commit()
            
        cur.close()
        conn.close()
        return {'success': True}
        
    return {'error': 'Error'}, 400


@app.route('/friends')
def friends():
    if 'username' not in session:
        return redirect(url_for('login'))
        
    usuario_actual = session['username']
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT a.id, a.usuario_origen, u.foto_perfil, u.estado 
        FROM amistades a
        JOIN usuarios u ON a.usuario_origen = u.username
        WHERE a.usuario_destino = %s AND a.estado = 'pendiente'
    """, (usuario_actual,))
    recibidas = cur.fetchall()

    cur.execute("""
        SELECT a.id, a.usuario_destino, u.foto_perfil, u.estado 
        FROM amistades a
        JOIN usuarios u ON a.usuario_destino = u.username
        WHERE a.usuario_origen = %s AND a.estado = 'pendiente'
    """, (usuario_actual,))
    enviadas = cur.fetchall()

    cur.execute("""
        SELECT a.id, u.username, u.foto_perfil, u.estado
        FROM amistades a
        JOIN usuarios u ON (
            (a.usuario_origen = %s AND u.username = a.usuario_destino) OR
            (a.usuario_destino = %s AND u.username = a.usuario_origen)
        )
        WHERE a.estado = 'aceptada'
    """, (usuario_actual, usuario_actual))
    amigos = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template('friends.html', recibidas=recibidas, enviadas=enviadas, amigos=amigos)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM usuarios WHERE (username = %s OR email = %s) AND password = %s", (username, username, password))
        user = cur.fetchone()
        cur.close()
        conn.close()
        
        if user:
            session['username'] = user[1]
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
    
    if not usuario:
        cur.close()
        conn.close()
        return "Este perfil no existe.", 404

    estado_amistad = None
    solicitud_id = None
    if 'username' in session and session['username'] != nombre_usuario:
        actual = session['username']
        cur.execute("""
            SELECT id, usuario_origen, estado FROM amistades 
            WHERE (usuario_origen = %s AND usuario_destino = %s) 
               OR (usuario_origen = %s AND usuario_destino = %s)
        """, (actual, nombre_usuario, nombre_usuario, actual))
        rel = cur.fetchone()
        if rel:
            solicitud_id = rel[0]
            if rel[2] == 'aceptada':
                estado_amistad = 'amigos'
            elif rel[1] == actual:
                estado_amistad = 'enviada'
            else:
                estado_amistad = 'recibida'

    cur.execute("""
        SELECT u.username, u.foto_perfil
        FROM amistades a
        JOIN usuarios u ON (
            (a.usuario_origen = %s AND u.username = a.usuario_destino) OR
            (a.usuario_destino = %s AND u.username = a.usuario_origen)
        )
        WHERE a.estado = 'aceptada'
    """, (nombre_usuario, nombre_usuario))
    amigos = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        'profile.html', 
        perfil=usuario, 
        estado_amistad=estado_amistad, 
        solicitud_id=solicitud_id, 
        amigos=amigos
    )


@app.route('/enviar_solicitud/<string:destino>', methods=['POST'])
def enviar_solicitud(destino):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    origen = session['username']
    if origen == destino:
        return redirect(url_for('profile', nombre_usuario=destino))
        
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT id FROM amistades 
        WHERE (usuario_origen = %s AND usuario_destino = %s) 
           OR (usuario_origen = %s AND usuario_destino = %s)
    """, (origen, destino, destino, origen))
    
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO amistades (usuario_origen, usuario_destino, estado) VALUES (%s, %s, 'pendiente')",
            (origen, destino)
        )
        conn.commit()
        
    cur.close()
    conn.close()
    return redirect(request.referrer or url_for('profile', nombre_usuario=destino))


@app.route('/responder_solicitud/<int:solicitud_id>/<string:accion>', methods=['POST'])
def responder_solicitud(solicitud_id, accion):
    if 'username' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cur = conn.cursor()
    
    if accion == 'aceptar':
        cur.execute(
            "UPDATE amistades SET estado = 'aceptada' WHERE id = %s AND usuario_destino = %s", 
            (solicitud_id, session['username'])
        )
    elif accion == 'rechazar':
        cur.execute("DELETE FROM amistades WHERE id = %s", (solicitud_id,))
        
    conn.commit()
    cur.close()
    conn.close()
    return redirect(request.referrer or url_for('inicio'))


@app.route('/edit_profile', methods=['GET', 'POST'])
def editar_perfil():
    if 'username' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()
    usuario_actual = session['username']

    if request.method == 'POST':
        nuevo_username = request.form['username'].strip()
        nueva_bio = request.form['biografia']
        nuevo_css = request.form['css_personalizado']
        nuevo_estado = request.form['estado']
        quitar_foto = request.form.get('quitar_foto')  
        
        foto = request.files.get('foto_perfil')
        ruta_foto = None
        
        if foto and foto.filename != '':
            filename = secure_filename(foto.filename)
            ruta_guardado = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            foto.save(ruta_guardado)
            ruta_foto = f"/static/uploads/{filename}"

        try:
            if nuevo_username != usuario_actual:
                cur.execute("SELECT ultima_actualizacion_nombre FROM usuarios WHERE username = %s", (usuario_actual,))
                res_fecha = cur.fetchone()
                ultima_vez = res_fecha[0] if res_fecha else None

                if ultima_vez:
                    from datetime import datetime, timedelta
                    if datetime.now() < ultima_vez + timedelta(days=3):
                        cur.close()
                        conn.close()
                        return "Error: Solo puedes cambiar tu nombre de usuario una vez cada 3 días. <a href='/edit_profile'>Volver</a>", 400

                cur.execute("SELECT id FROM usuarios WHERE username = %s", (nuevo_username,))
                if cur.fetchone():
                    cur.close()
                    conn.close()
                    return "Error: El nombre de usuario ya está en uso. <a href='/edit_profile'>Volver</a>", 400

                cur.execute("UPDATE usuarios SET username = %s, ultima_actualizacion_nombre = CURRENT_TIMESTAMP WHERE username = %s", (nuevo_username, usuario_actual))
                
                cur.execute("UPDATE amistades SET usuario_origen = %s WHERE usuario_origen = %s", (nuevo_username, usuario_actual))
                cur.execute("UPDATE amistades SET usuario_destino = %s WHERE usuario_destino = %s", (nuevo_username, usuario_actual))
                
                cur.execute("UPDATE publicaciones SET autor = %s WHERE autor = %s", (nuevo_username, usuario_actual))
                cur.execute("UPDATE comentarios_publicacion SET autor = %s WHERE autor = %s", (nuevo_username, usuario_actual))
                cur.execute("UPDATE likes_publicacion SET username = %s WHERE username = %s", (nuevo_username, usuario_actual))
                
                cur.execute("UPDATE mensajes SET remitente = %s WHERE remitente = %s", (nuevo_username, usuario_actual))
                cur.execute("UPDATE mensajes SET destinatario = %s WHERE destinatario = %s", (nuevo_username, usuario_actual))

                session['username'] = nuevo_username
                usuario_actual = nuevo_username

            if quitar_foto == 'si':
                cur.execute(
                    "UPDATE usuarios SET biografia = %s, css_personalizado = %s, estado = %s, foto_perfil = '/static/avatar.png' WHERE username = %s",
                    (nueva_bio, nuevo_css, nuevo_estado, usuario_actual)
                )
            elif ruta_foto:
                cur.execute(
                    "UPDATE usuarios SET biografia = %s, css_personalizado = %s, estado = %s, foto_perfil = %s WHERE username = %s",
                    (nueva_bio, nuevo_css, nuevo_estado, ruta_foto, usuario_actual)
                )
            else:
                cur.execute(
                    "UPDATE usuarios SET biografia = %s, css_personalizado = %s, estado = %s WHERE username = %s",
                    (nueva_bio, nuevo_css, nuevo_estado, usuario_actual)
                )
                
            conn.commit()
            
        except Exception as e:
            conn.rollback()
            cur.close()
            conn.close()
            return f"Hubo un error al actualizar el perfil: {e}"

        cur.close()
        conn.close()
        
        return redirect(url_for('profile', nombre_usuario=usuario_actual))

    cur.execute("SELECT username, biografia, css_personalizado, estado, foto_perfil FROM usuarios WHERE username = %s", (usuario_actual,))
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
                "INSERT INTO usuarios (username, email, password, foto_perfil) VALUES (%s, %s, %s, %s)",
                (username, email, password, '/static/avatar.png')
            )
            conn.commit()
            cur.close()
            conn.close()
            
            return redirect(url_for('login'))
            
        except Exception as e:
            return f"Hubo un error al registrar: {e}"

    return render_template('register.html')


@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    
    if query.startswith('@'):
        query = query[1:]
        
    if not query:
        return redirect(url_for('inicio'))
        
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT username, foto_perfil, estado FROM usuarios WHERE username ILIKE %s", ('%' + query + '%',))
    resultados = cur.fetchall()
    cur.close()
    conn.close()
    
    return render_template('search.html', resultados=resultados, query=query)


@app.route('/browse')
def browse():
    return render_template('browse.html')


@app.route('/messages', defaults={'destinatario': None}, methods=['GET', 'POST'])
@app.route('/messages/<string:destinatario>', methods=['GET', 'POST'])
def messages(destinatario):
    if 'username' not in session:
        return redirect(url_for('login'))

    usuario_actual = session['username']
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT u.username, u.foto_perfil, u.estado
        FROM amistades a
        JOIN usuarios u ON (
            (a.usuario_origen = %s AND a.usuario_destino = u.username) OR
            (a.usuario_destino = %s AND a.usuario_origen = u.username)
        )
        WHERE a.estado = 'aceptada'
    """, (usuario_actual, usuario_actual))
    contactos = cur.fetchall()

    datos_destinatario = None
    historial = []
    son_amigos = False

    if destinatario:
        cur.execute("SELECT username, foto_perfil, estado FROM usuarios WHERE username = %s", (destinatario,))
        datos_destinatario = cur.fetchone()

        cur.execute("""
            SELECT 1 FROM amistades
            WHERE ((usuario_origen = %s AND usuario_destino = %s)
               OR (usuario_origen = %s AND usuario_destino = %s))
              AND estado = 'aceptada'
        """, (usuario_actual, destinatario, destinatario, usuario_actual))
        son_amigos = cur.fetchone() is not None

        if request.method == 'POST' and son_amigos:
            contenido = request.form.get('contenido', '').strip()
            archivo = request.files.get('archivo')
            ruta_archivo = None

            if archivo and archivo.filename != '':
                filename = secure_filename(archivo.filename)
                ruta_guardado = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                archivo.save(ruta_guardado)
                ruta_archivo = f"/static/uploads/{filename}"

            if contenido or ruta_archivo:
                cur.execute("""
                    INSERT INTO mensajes (remitente, destinatario, contenido, imagen)
                    VALUES (%s, %s, %s, %s)
                """, (usuario_actual, destinatario, contenido, ruta_archivo))
                conn.commit()

            cur.close()
            conn.close()
            return redirect(url_for('messages', destinatario=destinatario))

        cur.execute("""
            SELECT remitente, contenido, imagen, TO_CHAR(fecha, 'HH24:MI - DD/MM'), id
            FROM mensajes
            WHERE (remitente = %s AND destinatario = %s)
               OR (remitente = %s AND destinatario = %s)
            ORDER BY fecha ASC
        """, (usuario_actual, destinatario, destinatario, usuario_actual))
        historial = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        'messages.html',
        contactos=contactos,
        destinatario=datos_destinatario,
        historial=historial,
        son_amigos=son_amigos
    )


@app.route('/editar_mensaje/<int:msg_id>', methods=['POST'])
def editar_mensaje(msg_id):
    if 'username' not in session:
        return {'error': 'No autorizado'}, 401
        
    usuario_actual = session['username']
    nuevo_contenido = request.form.get('contenido', '').strip()
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT remitente FROM mensajes WHERE id = %s", (msg_id,))
    msg = cur.fetchone()
    
    if msg and msg[0] == usuario_actual and nuevo_contenido:
        cur.execute("UPDATE mensajes SET contenido = %s WHERE id = %s", (nuevo_contenido, msg_id))
        conn.commit()
        
    cur.close()
    conn.close()
    return {'success': True, 'nuevo_contenido': nuevo_contenido}


@app.route('/eliminar_mensaje/<int:msg_id>', methods=['POST'])
def eliminar_mensaje(msg_id):
    if 'username' not in session:
        return {'error': 'No autorizado'}, 401
        
    usuario_actual = session['username']
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT remitente FROM mensajes WHERE id = %s", (msg_id,))
    msg = cur.fetchone()
    
    if msg and msg[0] == usuario_actual:
        cur.execute("DELETE FROM mensajes WHERE id = %s", (msg_id,))
        conn.commit()
        
    cur.close()
    conn.close()
    return {'success': True}


@app.route('/blog')
def blog():
    return render_template('blog.html')


@app.route('/forum')
def forum():
    return render_template('forum.html')


@app.route('/groups')
def groups():
    return render_template('groups.html')


# ================= PANEL DE ADMINISTRACIÓN DEL CREADOR =================

@app.route('/admin')
def panel_admin():
    if 'username' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT es_admin FROM usuarios WHERE username = %s", (session['username'],))
    res = cur.fetchone()

    if not res or not res[0]:
        cur.close()
        conn.close()
        return "Acceso denegado: Área exclusiva del Creador.", 403

    cur.execute("SELECT id, username, foto_perfil, estado, es_admin FROM usuarios ORDER BY id ASC")
    usuarios = cur.fetchall()

    cur.execute("SELECT id, autor, descripcion, archivo, TO_CHAR(fecha, 'DD/MM/YYYY HH24:MI') FROM publicaciones ORDER BY id DESC")
    publicaciones = cur.fetchall()

    cur.execute("SELECT id, publicacion_id, autor, comentario, TO_CHAR(fecha, 'DD/MM/YYYY HH24:MI') FROM comentarios_publicacion ORDER BY id DESC")
    comentarios = cur.fetchall()

    cur.close()
    conn.close()
    return render_template('admin.html', usuarios=usuarios, publicaciones=publicaciones, comentarios=comentarios)


@app.route('/admin/eliminar_publicacion/<int:pub_id>', methods=['POST'])
def admin_eliminar_publicacion(pub_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT es_admin FROM usuarios WHERE username = %s", (session['username'],))
    res = cur.fetchone()

    if res and res[0]:
        cur.execute("DELETE FROM likes_publicacion WHERE publicacion_id = %s", (pub_id,))
        cur.execute("DELETE FROM comentarios_publicacion WHERE publicacion_id = %s", (pub_id,))
        cur.execute("DELETE FROM publicaciones WHERE id = %s", (pub_id,))
        conn.commit()

    cur.close()
    conn.close()
    return redirect(request.referrer or url_for('panel_admin'))


@app.route('/admin/eliminar_comentario/<int:com_id>', methods=['POST'])
def admin_eliminar_comentario(com_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT es_admin FROM usuarios WHERE username = %s", (session['username'],))
    res = cur.fetchone()

    if res and res[0]:
        cur.execute("DELETE FROM comentarios_publicacion WHERE id = %s", (com_id,))
        conn.commit()

    cur.close()
    conn.close()
    return redirect(request.referrer or url_for('panel_admin'))


@app.route('/admin/eliminar_usuario/<string:target_user>', methods=['POST'])
def admin_eliminar_usuario(target_user):
    if 'username' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT es_admin FROM usuarios WHERE username = %s", (session['username'],))
    res = cur.fetchone()

    if res and res[0] and target_user != session['username']:
        cur.execute("DELETE FROM likes_publicacion WHERE username = %s", (target_user,))
        cur.execute("DELETE FROM comentarios_publicacion WHERE autor = %s", (target_user,))
        cur.execute("DELETE FROM likes_publicacion WHERE publicacion_id IN (SELECT id FROM publicaciones WHERE autor = %s)", (target_user,))
        cur.execute("DELETE FROM comentarios_publicacion WHERE publicacion_id IN (SELECT id FROM publicaciones WHERE autor = %s)", (target_user,))
        cur.execute("DELETE FROM publicaciones WHERE autor = %s", (target_user,))
        cur.execute("DELETE FROM mensajes WHERE remitente = %s OR destinatario = %s", (target_user, target_user))
        cur.execute("DELETE FROM amistades WHERE usuario_origen = %s OR usuario_destino = %s", (target_user, target_user))
        cur.execute("DELETE FROM usuarios WHERE username = %s", (target_user,))
        conn.commit()

    cur.close()
    conn.close()
    return redirect(url_for('panel_admin'))


if __name__ == '__main__':
    app.run(debug=True)